from devpi_server.config import hookimpl
from devpi_server.model import InvalidIndex
from devpi_server.model import InvalidIndexconfig
from devpi_server.model import PrivateStage


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
            if oldconfig["state"] == "new" and newconfig["state"] != "pending":
                errors.append("The merge index isn't in state 'pending'")
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


@hookimpl
def devpiserver_get_stage_class():
    return ("merge", MergeStage)


@hookimpl
def devpiserver_indexconfig_defaults(index_type):
    if index_type == "mirror":
        return {}
    if index_type == "stage":
        return {
            'push_requests_allowed': False}
    return {
        'state': 'new',
        'messages': []}
