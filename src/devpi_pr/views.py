from devpi_server.views import apireturn
from pyramid.view import view_config


@view_config(route_name="index-pr-list", request_method="GET")
def index_pr_list(context, request):
    result = {}
    if not context.stage.ixconfig.get("push_requests_allowed", False):
        apireturn(200, type="pr-list", result=result)
    targetindex_name = context.stage.name
    for user in context.model.get_userlist():
        for name, ixconfig in user.get()["indexes"].items():
            if ixconfig["type"] != "merge":
                continue
            if targetindex_name not in ixconfig['bases']:
                continue
            stage = user.getstage(name)
            last_serial = stage.get_last_change_serial()
            state_info = result.setdefault(ixconfig["states"][-1], {})
            state_info.setdefault(user.name, []).append(dict(
                name=name,
                base=targetindex_name,
                last_serial=last_serial))
    apireturn(200, type="pr-list", result=result)


@view_config(route_name="user-pr-list", request_method="GET")
def user_pr_list(context, request):
    result = {}
    user = context.user
    for name, ixconfig in user.get()["indexes"].items():
        if ixconfig["type"] != "merge":
            continue
        stage = user.getstage(name)
        last_serial = stage.get_last_change_serial()
        (targetindex_name,) = ixconfig["bases"]
        state_info = result.setdefault(ixconfig["states"][-1], {})
        state_info.setdefault(user.name, []).append(dict(
            name=name,
            base=targetindex_name,
            last_serial=last_serial))
    apireturn(200, type="pr-list", result=result)
