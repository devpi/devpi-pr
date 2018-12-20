import pytest
try:
    from devpi_server import __version__  # noqa
except ImportError:
    pytestmark = pytest.mark.skip("No devpi-server installed")
else:
    from test_devpi_server.conftest import gentmp  # noqa
    from test_devpi_server.conftest import httpget  # noqa
    from test_devpi_server.conftest import makemapp  # noqa
    from test_devpi_server.conftest import maketestapp  # noqa
    from test_devpi_server.conftest import makexom  # noqa
    from test_devpi_server.conftest import mapp  # noqa
    from test_devpi_server.conftest import pypiurls  # noqa
    from test_devpi_server.conftest import storage_info  # noqa
    from test_devpi_server.conftest import testapp  # noqa

    (makexom, mapp, testapp)  # shut up pyflakes


@pytest.fixture
def xom(request, makexom):
    import devpi_pr.server
    xom = makexom(plugins=[
        (devpi_pr.server, None)])
    return xom


@pytest.fixture
def targetindex(mapp, testapp):
    mapp.create_and_login_user("targetuser")
    result = mapp.create_index("targetindex")
    r = testapp.get_json(result.index)
    assert r.json["result"]["push_requests_allowed"] is False
    r = testapp.patch_json(result.index, dict(
        r.json["result"],
        push_requests_allowed=True))
    assert r.json["result"]["push_requests_allowed"] is True
    return result


@pytest.fixture
def mergeindex(mapp, targetindex):
    mapp.create_and_login_user("mergeuser")
    api = mapp.create_index(
        "+pr-index",
        indexconfig=dict(
            type="merge",
            bases=[targetindex.stagename]))
    return api


def test_new_merge_index(mergeindex, targetindex, testapp):
    r = testapp.get_json(mergeindex.index)
    result = r.json['result']
    assert result['type'] == 'merge'
    assert result['acl_upload'] == ['mergeuser']
    assert result['bases'] == [targetindex.stagename]
    assert result['messages'] == []
    assert result['state'] == 'new'


def test_submit_merge_index_not_allowed(mapp, mergeindex, targetindex, testapp):
    # first turn off push_requests_allowed
    mapp.login(targetindex.stagename.split('/')[0], "123")
    r = testapp.get_json(targetindex.index)
    r = testapp.patch_json(targetindex.index, dict(
        r.json["result"],
        push_requests_allowed=False))
    assert r.json["result"]["push_requests_allowed"] is False
    # now try to submit
    mapp.login(mergeindex.stagename.split('/')[0], "123")
    r = testapp.patch_json(mergeindex.index, [
        'state=pending',
        'messages+=Please approve'], expect_errors=True)
    assert r.json["message"] == "The target index '%s' doesn't allow push requests" % targetindex.stagename


def test_submit_merge_index(mergeindex, targetindex, testapp):
    r = testapp.patch_json(mergeindex.index, [
        'state=pending',
        'messages+=Please approve'])
    r = testapp.get_json(mergeindex.index)
    result = r.json['result']
    assert result['type'] == 'merge'
    assert result['acl_upload'] == ['mergeuser']
    assert result['bases'] == [targetindex.stagename]
    assert result['messages'] == ['Please approve']
    assert result['state'] == 'pending'


@pytest.mark.parametrize("targetstate", ["approved", "rejected"])
def test_invalid_state_changes_from_new(mergeindex, targetstate, testapp):
    r = testapp.patch_json(mergeindex.index, [
        'state=%s' % targetstate,
        'messages+=Change'], expect_errors=True)
    assert r.json["message"] == "State transition from 'new' to '%s' not allowed" % targetstate


def test_approve_pending_not_possible_for_mergeuser(mergeindex, targetindex, testapp):
    r = testapp.patch_json(mergeindex.index, [
        'state=pending',
        'messages+=Please approve'])
    r = testapp.patch_json(mergeindex.index, [
        'state=approved',
        'messages+=Approve'], expect_errors=True)
    assert r.json["message"] == "user 'mergeuser' cannot upload to '%s'" % targetindex.stagename


def test_approve_pending(mapp, mergeindex, targetindex, testapp):
    r = testapp.patch_json(mergeindex.index, [
        'state=pending',
        'messages+=Please approve'])
    mapp.login(targetindex.stagename.split('/')[0], "123")
    r = testapp.patch_json(mergeindex.index, [
        'state=approved',
        'messages+=Approve'], expect_errors=True)
    result = r.json['result']
    assert result['type'] == 'merge'
    assert result['acl_upload'] == ['mergeuser']
    assert result['bases'] == [targetindex.stagename]
    assert result['messages'] == ['Please approve', 'Approve']
    assert result['state'] == 'approved'


def test_reject_pending_not_possible_for_mergeuser(mergeindex, testapp):
    r = testapp.patch_json(mergeindex.index, [
        'state=pending',
        'messages+=Please approve'])
    r = testapp.patch_json(mergeindex.index, [
        'state=rejected',
        'messages+=Reject'], expect_errors=True)
    assert r.json["message"] == "State transition to 'rejected' not authorized"


def test_cancel_pending(mergeindex, targetindex, testapp):
    r = testapp.patch_json(mergeindex.index, [
        'state=pending',
        'messages+=Please approve'])
    r = testapp.patch_json(mergeindex.index, [
        'state=new',
        'messages+=Cancel'], expect_errors=True)
    result = r.json['result']
    assert result['type'] == 'merge'
    assert result['acl_upload'] == ['mergeuser']
    assert result['bases'] == [targetindex.stagename]
    assert result['messages'] == ['Please approve', 'Cancel']
    assert result['state'] == 'new'


def test_pr_list(mapp, mergeindex, targetindex, testapp):
    r = testapp.get_json(targetindex.index + "/+pr-list")
    result = r.json['result']
    assert result == {'new': {'mergeuser': [['index', 5]]}}
    r = testapp.patch_json(mergeindex.index, [
        'state=pending',
        'messages+=Please approve'])
    r = testapp.get_json(targetindex.index + "/+pr-list")
    result = r.json['result']
    assert result == {'pending': {'mergeuser': [['index', 6]]}}


def test_pr_list_serial(mapp, mergeindex, targetindex, testapp):
    r = testapp.get_json(targetindex.index + "/+pr-list")
    result = r.json['result']
    assert result == {'new': {'mergeuser': [['index', 5]]}}
    content1 = mapp.makepkg("hello-1.0.tar.gz", b"content1", "hello", "1.0")
    mapp.upload_file_pypi(
        "hello-1.0.tar.gz", content1, "hello", "1.0",
        set_whitelist=False)
    r = testapp.get_json(targetindex.index + "/+pr-list")
    result = r.json['result']
    # serial 6 is registration, serial 7 is the upload
    assert result == {'new': {'mergeuser': [['index', 7]]}}
    r = testapp.patch_json(mergeindex.index, [
        'state=pending',
        'messages+=Please approve'])
    r = testapp.get_json(targetindex.index + "/+pr-list")
    result = r.json['result']
    assert result == {'pending': {'mergeuser': [['index', 8]]}}
    content2 = mapp.makepkg("hello-1.0.zip", b"content2", "hello", "1.0")
    mapp.upload_file_pypi(
        "hello-1.0.zip", content2, "hello", "1.0",
        set_whitelist=False)
    r = testapp.get_json(targetindex.index + "/+pr-list")
    result = r.json['result']
    assert result == {'pending': {'mergeuser': [['index', 9]]}}
