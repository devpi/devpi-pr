from devpi_server.log import threadlog as log
from devpi_server.views import apireturn
from pyramid.view import view_config


@view_config(route_name="pr-list", request_method="GET")
def pr_list(context, request):
    result = {}
    targetindex_name = None
    if context.stage.ixconfig.get("push_requests_allowed", False):
        targetindex_name = context.stage.name
    for user in context.model.get_userlist():
        for name, ixconfig in user.get()["indexes"].items():
            if ixconfig["type"] != "merge":
                continue
            state = ixconfig["states"][-1]
            add_index = False
            log.debug(
                "pr_list user.name: %s name: %s auth_id: %s state: %s",
                user.name, name, request.authenticated_userid, state)
            if user.name == request.authenticated_userid:
                add_index = True
            if targetindex_name in ixconfig['bases']:
                add_index = True
            if add_index is False:
                continue
            stage = user.getstage(name)
            last_serial = stage.get_last_change_serial()
            (base,) = ixconfig['bases']
            state_info = result.setdefault(ixconfig["states"][-1], {})
            state_info.setdefault(user.name, []).append(dict(
                name=name,
                base=base,
                last_serial=last_serial))
    apireturn(200, type="pr-list", result=result)
