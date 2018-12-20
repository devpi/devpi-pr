from devpi_server.views import apireturn
from pyramid.view import view_config


@view_config(route_name="pr-list", request_method="GET")
def pr_list(context, request):
    result = {}
    if not context.stage.ixconfig.get("push_requests_allowed", False):
        apireturn(
            400, "Push requests to '%s' not allowed" % context.stage.name)
    for user in context.model.get_userlist():
        for name, ixconfig in user.get()["indexes"].items():
            if ixconfig["type"] != "merge":
                continue
            if context.stage.name not in ixconfig['bases']:
                continue
            stage = user.getstage(name)
            last_serial = user.key.last_serial
            for project in stage.list_projects_perstage():
                project_serial = stage.key_projsimplelinks(project).last_serial
                if project_serial is None:
                    continue
                last_serial = max(last_serial, project_serial)
            state_info = result.setdefault(ixconfig["states"][-1], {})
            state_info.setdefault(user.name, []).append((name[4:], last_serial))
    apireturn(200, type="pr-list", result=result)
