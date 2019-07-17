from devpi_server.model import ensure_list
from pluggy import HookimplMarker
import json


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


class PRStage(object):
    @classmethod
    def get_possible_indexconfig_keys(cls):
        """ Returns all possible custom index config keys. """
        return ('states', 'messages', 'changers')

    def get_default_config_items(self):
        return [("changers", [self.stage.username])]

    def normalize_indexconfig_value(self, key, value):
        if key in ("messages", "states", "changers"):
            return ensure_list(value)

    def validate_config(self, oldconfig, newconfig):
        errors = []
        newstate = newconfig["states"][-1]
        if newstate == "pending":
            target = self.stage.xom.model.getstage(newconfig["bases"][0])
            if not target.ixconfig.get("pull_requests_allowed", False):
                errors.append(
                    "The target index '%s' doesn't allow "
                    "pull requests" % target.name)
            if is_stage_empty(self.stage):
                errors.append(
                    "The pr index has no packages")
        new_states_count = len(newconfig["states"])
        new_message_count = len(newconfig["messages"])
        if new_states_count != new_message_count:
            errors.append(
                "The number of states and messages must match for a pr index")
        if set(oldconfig.keys()) == set(['type']):
            # creating new stage
            assert newconfig["type"] == "pr"
            if newconfig["states"][0] != "new":
                errors.append("A new pr index must have state 'new'")
        else:
            new_state_count = len(newconfig["states"])
            old_message_count = len(oldconfig["messages"])
            oldstate = oldconfig["states"][-1]
            old_state_count = len(oldconfig["states"])
            if oldstate != newstate:
                if new_message_count != old_message_count + 1:
                    errors.append("A state change on a pr index requires a message")
            elif old_state_count != new_state_count:
                errors.append(
                    "State transition from '%s' to '%s' not allowed" % (
                        oldstate, newstate))
            if old_message_count > new_message_count:
                errors.append("Messages can't be removed from pr index")
            if oldconfig["messages"] != newconfig["messages"][:old_message_count]:
                errors.append("Existing messages can't be modified")
            if list(oldconfig["bases"]) != list(newconfig["bases"]):
                errors.append("The bases of a pr index can't be changed")
            if oldstate != newstate:
                new_states = states[oldstate]
                if newstate not in new_states:
                    errors.append(
                        "State transition from '%s' to '%s' not allowed" % (
                            oldstate, newstate))
            if len(newconfig["bases"]) != 1:
                errors.append("A pr index must have exactly one base")
            new_changers_count = len(newconfig["changers"])
            old_changers_count = len(oldconfig["changers"])
            if old_changers_count != new_changers_count:
                errors.append(
                    "The changers setting is automatically generated, "
                    "it is not allowed to be changed")
        if errors:
            raise self.InvalidIndexconfig(errors)

    def _get_target_stage(self):
        ixconfig = self.stage.ixconfig
        targetindex = ixconfig["bases"][0]
        return self.stage.model.getstage(*targetindex.split("/"))

    def get_principals_for_index_delete(self, **kwargs):
        principals = super(PRStage, self).get_principals_for_index_delete(**kwargs)
        state = self.stage.ixconfig['states'][-1]
        if state == 'approved':
            # when approved, the principals in the target acl_upload are
            # allowed to delete this index
            target = self._get_target_stage()
            principals.update(target.ixconfig.get('acl_upload', []))
        return principals

    def get_principals_for_index_modify(self, **kwargs):
        principals = super(PRStage, self).get_principals_for_index_modify(**kwargs)
        state = self.stage.ixconfig['states'][-1]
        if state == 'pending':
            # when pending, the principals in the target acl_upload are
            # allowed to modify this index to change it's state etc
            target = self._get_target_stage()
            principals.update(target.ixconfig.get('acl_upload', []))
        return principals

    def on_modified(self, request, oldconfig):
        ixconfig = self.stage.ixconfig
        if not oldconfig:
            # just created
            ixconfig["changers"] = [request.authenticated_userid]
            return
        target = self._get_target_stage()
        state = ixconfig["states"][-1]
        if state == "approved":
            pr_serial = request.headers.get('X-Devpi-PR-Serial')
            try:
                pr_serial = int(pr_serial)
            except TypeError:
                request.apifatal(
                    400, message="missing X-Devpi-PR-Serial request header")
            last_serial = self.stage.get_last_change_serial()
            if pr_serial != last_serial:
                request.apifatal(
                    400, message="got X-Devpi-PR-Serial %s, expected %s" % (
                        pr_serial, last_serial))
            if not request.has_permission("pypi_submit", context=target):
                request.apifatal(401, message="user %r cannot upload to %r" % (
                    request.authenticated_userid, target.name))
            for project in self.stage.list_projects_perstage():
                version = self.stage.get_latest_version_perstage(project)
                linkstore = self.stage.get_linkstore_perstage(project, version)
                target.set_versiondata(linkstore.metadata)
                toxresults = {}
                for link in linkstore.get_links(rel='toxresult'):
                    toxresults.setdefault(link.for_entrypath, []).append(link)
                for link in linkstore.get_links():
                    try:
                        if link.rel == 'doczip':
                            new_link = target.store_doczip(
                                project, version,
                                link.entry.file_get_content())
                            new_link.add_logs(
                                x for x in link.get_logs()
                                if x.get('what') != 'overwrite')
                            new_link.add_log(
                                'push',
                                request.authenticated_userid,
                                src=self.stage.name,
                                dst=target.name,
                                message=ixconfig['messages'][-1])
                        elif link.rel == 'releasefile':
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
                            for tox_link in toxresults.get(link.relpath, []):
                                new_tox_link = target.store_toxresult(
                                    new_link,
                                    json.loads(
                                        tox_link.entry.file_get_content().decode('utf-8')))
                                new_tox_link.add_logs(
                                    x for x in tox_link.get_logs()
                                    if x.get('what') != 'overwrite')
                                new_tox_link.add_log(
                                    'push',
                                    request.authenticated_userid,
                                    src=self.stage.name,
                                    dst=target.name,
                                    message=ixconfig['messages'][-1])
                        else:
                            continue
                    except target.NonVolatile as e:
                        request.apifatal(
                            409, "%s already exists in non-volatile index" % (
                                e.link.basename,))
        elif state == "rejected":
            if not request.has_permission("pypi_submit", context=target):
                raise self.InvalidIndexconfig([
                    "State transition to '%s' "
                    "not authorized" % state])
        old_state = oldconfig["states"][-1]
        if old_state != state:
            ixconfig["changers"].append(request.authenticated_userid)


@server_hookimpl
def devpiserver_get_stage_customizer_classes():
    return [("pr", PRStage)]


@server_hookimpl
def devpiserver_indexconfig_defaults(index_type):
    if index_type == "stage":
        return {
            'pull_requests_allowed': False}
    return {}


def includeme(config):
    config.add_route("index-pr-list", "/{user}/{index}/+pr-list")
    config.add_route("user-pr-list", "/{user}/+pr-list")
    config.scan('devpi_pr.views')


@server_hookimpl
def devpiserver_pyramid_configure(config, pyramid_config):
    # by using include, the package name doesn't need to be set explicitly
    # for registrations of static views etc
    pyramid_config.include('devpi_pr.server')
