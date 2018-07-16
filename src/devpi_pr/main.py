from devpi_server.model import InvalidIndex, PrivateStage


class MergeStage(PrivateStage):
    @classmethod
    def verify_name(cls, indexname):
        if not indexname.startswith('+pr-'):
            raise InvalidIndex(
                "indexname '%s' must start with '+pr-'." % indexname)
        PrivateStage.verify_name(indexname[4:])


def devpiserver_get_stage_class():
    return ("merge", MergeStage)


def devpiserver_indexconfig_defaults(index_type):
    if index_type != "merge":
        return {}
    return {
        'state': 'new',
        'messages': []}
