from devpi_server.readonly import get_mutable_deepcopy


def get_last_serial_for_merge_index(stage, current_index_config=None):
    assert stage.ixconfig["type"] == "merge"
    keyfs = stage.keyfs
    user_key = stage.user.key
    if current_index_config is None:
        current_index_config = stage.ixconfig
    last_serial = stage.key_projects.last_serial
    if last_serial is None:
        last_serial = -1
    # first we find the newest project serial
    for project in stage.list_projects_perstage():
        project_serial = stage.key_projsimplelinks(project).last_serial
        if project_serial is None:
            continue
        last_serial = max(last_serial, project_serial)
    # if any project is newer than the user config, we are done
    user_serial = user_key.last_serial
    if last_serial >= user_serial:
        return last_serial
    # otherwise we search for the last serial at which the index config was changed
    for serial, user_config in keyfs.tx.iter_serial_and_value_backwards(user_key):
        if user_serial < last_serial:
            break
        index_config = get_mutable_deepcopy(
            user_config["indexes"].get(stage.index, {}))
        if current_index_config == index_config:
            user_serial = serial
            continue
        last_serial = user_serial
        break
    return last_serial
