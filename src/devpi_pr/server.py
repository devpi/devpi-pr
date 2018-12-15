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
        messages = []
        if not oldconfig:
            # creating new stage
            assert newconfig["type"] == "merge"
        if len(newconfig["bases"]) != 1:
            messages.append("A merge index must have exactly one base")
        if messages:
            raise InvalidIndexconfig(messages)


def devpiserver_get_stage_class():
    return ("merge", MergeStage)


def devpiserver_indexconfig_defaults(index_type):
    if index_type != "merge":
        return {}
    return {
        'state': 'new',
        'messages': []}
