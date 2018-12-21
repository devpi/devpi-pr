def get_last_serial_for_merge_index(stage):
    assert stage.ixconfig["type"] == "merge"
    last_serial = stage.user.key.last_serial
    for project in stage.list_projects_perstage():
        project_serial = stage.key_projsimplelinks(project).last_serial
        if project_serial is None:
            continue
        last_serial = max(last_serial, project_serial)
    return last_serial
