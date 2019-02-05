from .utils import get_last_serial_for_merge_index
from devpi_server.model import BaseStageCustomizer
from devpi_server.model import ensure_list
from devpi_server.model import is_valid_name
from pluggy import HookimplMarker


server_hookimpl = HookimplMarker("devpiserver")


states = {
    'new': set(['pending']),
    'pending': set(['approved', 'new', 'rejected']),
    'approved': set([]),
    'rejected': set(['pending']),
}


def is_stage_empty(stage):
    for project in stage.list_projects_perstage():
        if stage.get_releaselinks_perstage(project):
            return False
    return True


class MergeStage(BaseStageCustomizer):
    def verify_name(self, indexname):
        if not indexname.startswith('+pr-'):
            raise self.InvalidIndex(
                "indexname '%s' must start with '+pr-'." % indexname)
        if not is_valid_name(indexname[4:]):
            raise self.InvalidIndex(
                "indexname '%s' contains characters that aren't allowed. "
                "Any ascii symbol besides -.@_ after '+pr-' is blocked." % indexname[4:])

    def get_indexconfig_items(self, **kwargs):
        errors = []
        ixconfig = {}
        if not kwargs.get("states"):
            errors.append("A merge index requires a state")
        else:
            ixconfig["states"] = ensure_list(kwargs.pop("states"))
        if not kwargs.get("messages"):
            errors.append("A merge index requires messages")
        else:
            ixconfig["messages"] = ensure_list(kwargs.pop("messages"))
        if errors:
            raise self.InvalidIndexconfig(errors)
        return ixconfig.items()

    def validate_ixconfig(self, oldconfig, newconfig):
        errors = []
        newstate = newconfig["states"][-1]
        if newstate == "pending":
            target = self.stage.xom.model.getstage(newconfig["bases"][0])
            if not target.ixconfig.get("push_requests_allowed", False):
                errors.append(
                    "The target index '%s' doesn't allow "
                    "push requests" % target.name)
            if is_stage_empty(self.stage):
                errors.append(
                    "The merge index has no packages")
        new_states_count = len(newconfig["states"])
        new_message_count = len(newconfig["messages"])
        if new_states_count != new_message_count:
            errors.append(
                "The number of states and messages must match for a merge index")
        if set(oldconfig.keys()) == set(['type']):
            # creating new stage
            assert newconfig["type"] == "merge"
            if newstate != "new":
                errors.append("A new merge index must have state 'new'")
        else:
            new_state_count = len(newconfig["states"])
            old_message_count = len(oldconfig["messages"])
            oldstate = oldconfig["states"][-1]
            old_state_count = len(oldconfig["states"])
            if oldstate != newstate:
                if new_message_count != old_message_count + 1:
                    errors.append("A state change on a merge index requires a message")
            elif old_state_count != new_state_count:
                errors.append(
                    "State transition from '%s' to '%s' not allowed" % (
                        oldstate, newstate))
            if old_message_count > new_message_count:
                errors.append("Messages can't be removed from merge index")
            if oldconfig["messages"] != newconfig["messages"][:old_message_count]:
                errors.append("Existing messages can't be modified")
            if list(oldconfig["bases"]) != list(newconfig["bases"]):
                errors.append("The bases of a merge index can't be changed")
            if oldstate != newstate:
                new_states = states[oldstate]
                if newstate not in new_states:
                    errors.append(
                        "State transition from '%s' to '%s' not allowed" % (
                            oldstate, newstate))
        if len(newconfig["bases"]) != 1:
            errors.append("A merge index must have exactly one base")
        if errors:
            raise self.InvalidIndexconfig(errors)

    def ixconfig_pre_modify(self, request):
        pass

    def ixconfig_post_modify(self, request, oldconfig):
        context = request.context
        ixconfig = self.stage.ixconfig
        targetindex = ixconfig["bases"][0]
        target = context.getstage(*targetindex.split("/"))
        state = ixconfig["states"][-1]
        if state == "approved":
            pr_serial = request.headers.get('X-Devpi-PR-Serial')
            try:
                pr_serial = int(pr_serial)
            except TypeError:
                request.apifatal(
                    400, message="missing X-Devpi-PR-Serial request header")
            merge_serial = get_last_serial_for_merge_index(self.stage)
            if pr_serial != merge_serial:
                request.apifatal(
                    400, message="got X-Devpi-PR-Serial %s, expected %s" % (
                        pr_serial, merge_serial))
            if not request.has_permission("pypi_submit", context=target):
                request.apifatal(401, message="user %r cannot upload to %r" % (
                    request.authenticated_userid, target.name))
            for project in self.stage.list_projects_perstage():
                version = self.stage.get_latest_version_perstage('hello')
                linkstore = self.stage.get_linkstore_perstage(project, version)
                target.set_versiondata(linkstore.metadata)
                for link in linkstore.get_links():
                    if link.rel == 'doczip':
                        new_link = target.store_doczip(
                            project, version,
                            link.entry.file_get_content())
                    else:
                        new_link = target.store_releasefile(
                            project, version,
                            link.basename, link.entry.file_get_content(),
                            last_modified=link.entry.last_modified)
                    new_link.add_logs(
                        x for x in link.get_logs()
                        if x.get('what') != 'overwrite')
                    new_link.add_log(
                        'push',
                        request.authenticated_userid,
                        src=self.stage.name,
                        dst=target.name,
                        message=ixconfig['messages'][-1])
        elif state == "rejected":
            if not request.has_permission("pypi_submit", context=target):
                raise self.InvalidIndexconfig([
                    "State transition to '%s' "
                    "not authorized" % state])
        else:
            if not request.has_permission("index_modify"):
                request.apifatal(403, "not allowed to modify index")


@server_hookimpl
def devpiserver_get_stage_customizer_classes():
    return [("merge", MergeStage)]


@server_hookimpl
def devpiserver_indexconfig_defaults(index_type):
    if index_type == "mirror":
        return {}
    if index_type == "stage":
        return {
            'push_requests_allowed': False}
    return {
        'states': [],
        'messages': []}
    return {}


def includeme(config):
    config.add_route("pr-list", "/{user}/{index}/+pr-list")
    config.scan('devpi_pr.views')


@server_hookimpl
def devpiserver_pyramid_configure(config, pyramid_config):
    # by using include, the package name doesn't need to be set explicitly
    # for registrations of static views etc
    pyramid_config.include('devpi_pr.server')
