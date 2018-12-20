from devpi_server.model import BaseStageCustomizer
from devpi_server.model import ensure_list
from devpi_server.model import is_valid_name
from devpi_server.views import apireturn
from pluggy import HookimplMarker


server_hookimpl = HookimplMarker("devpiserver")


states = {
    'new': set(['pending']),
    'pending': set(['approved', 'new', 'rejected']),
    'approved': set([]),
    'rejected': set(['pending']),
}


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
            old_message_count = len(oldconfig["messages"])
            oldstate = oldconfig["states"][-1]
            if oldstate != newstate:
                if new_message_count != old_message_count + 1:
                    errors.append("A state change on a merge index requires a message")
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
            if not request.has_permission("pypi_submit", context=target):
                apireturn(401, message="user %r cannot upload to %r" % (
                    request.authenticated_userid, target.name))
        elif state == "rejected":
            if not request.has_permission("pypi_submit", context=target):
                raise self.InvalidIndexconfig([
                    "State transition to '%s' "
                    "not authorized" % state])
        else:
            if not request.has_permission("index_modify"):
                apireturn(403, "not allowed to modify index")


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
