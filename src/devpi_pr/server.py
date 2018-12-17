from devpi_server.model import InvalidIndex
from devpi_server.model import InvalidIndexconfig
from devpi_server.model import PrivateStage
from devpi_server.views import apireturn
from pluggy import HookimplMarker


server_hookimpl = HookimplMarker("devpiserver")


states = {
    'new': set(['pending']),
    'pending': set(['approved', 'new', 'rejected']),
    'approved': set([]),
    'rejected': set(['pending']),
}


class MergeStage(PrivateStage):
    @classmethod
    def verify_name(cls, indexname):
        if not indexname.startswith('+pr-'):
            raise InvalidIndex(
                "indexname '%s' must start with '+pr-'." % indexname)
        PrivateStage.verify_name(indexname[4:])

    @classmethod
    def validate_ixconfig(cls, oldconfig, newconfig):
        errors = []
        new_message_count = len(newconfig["messages"])
        if not oldconfig:
            # creating new stage
            assert newconfig["type"] == "merge"
            if newconfig["state"] != "new":
                errors.append("A new merge index must have state 'new'")
        else:
            old_message_count = len(oldconfig["messages"])
            if oldconfig["state"] != newconfig["state"]:
                if new_message_count != old_message_count + 1:
                    errors.append("A state change on a merge index requires a message")
            if old_message_count > new_message_count:
                errors.append("Messages can't be removed from merge index")
            if oldconfig["messages"] != newconfig["messages"][:old_message_count]:
                errors.append("Existing messages can't be modified")
            if list(oldconfig["bases"]) != list(newconfig["bases"]):
                errors.append("The bases of a merge index can't be changed")
            new_states = states[oldconfig["state"]]
            if newconfig["state"] not in new_states:
                errors.append(
                    "State transition from '%s' to '%s' not allowed" % (
                        oldconfig["state"], newconfig["state"]))
        if len(newconfig["bases"]) != 1:
            errors.append("A merge index must have exactly one base")
        if errors:
            raise InvalidIndexconfig(errors)

    def modify_ixconfig(self, ixconfig):
        if ixconfig["state"] == "pending":
            target = self.xom.model.getstage(ixconfig["bases"][0])
            if not target.ixconfig.get("push_requests_allowed", False):
                raise InvalidIndexconfig([
                    "The target index '%s' doesn't allow "
                    "push requests" % target.name])

    def auth_ixconfig(self, request, ixconfig):
        if ixconfig["state"] == "approved":
            target = self.xom.model.getstage(ixconfig["bases"][0])
            if not request.has_permission("pypi_submit", context=target):
                apireturn(401, message="user %r cannot upload to %r" % (
                    request.authenticated_userid, target.name))
        if ixconfig["state"] == "rejected":
            target = self.xom.model.getstage(ixconfig["bases"][0])
            if not request.has_permission("pypi_submit", context=target):
                raise InvalidIndexconfig([
                    "State transition to '%s' "
                    "not authorized" % ixconfig["state"]])


@server_hookimpl
def devpiserver_get_stage_class():
    return ("merge", MergeStage)


@server_hookimpl
def devpiserver_indexconfig_defaults(index_type):
    if index_type == "mirror":
        return {}
    if index_type == "stage":
        return {
            'push_requests_allowed': False}
    return {
        'state': 'new',
        'messages': []}
