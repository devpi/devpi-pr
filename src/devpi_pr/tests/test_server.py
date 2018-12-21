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
def new_mergeindex(mapp, targetindex):
    mapp.create_and_login_user("mergeuser")
    api = mapp.create_index(
        "+pr-index",
        indexconfig=dict(
            type="merge",
            states="new",
            messages="New push request",
            bases=[targetindex.stagename]))
    return api


@pytest.fixture
def mergeindex(mapp, new_mergeindex, targetindex, testapp):
    content1 = mapp.makepkg("hello-1.0.tar.gz", b"content1", "hello", "1.0")
    mapp.upload_file_pypi(
        "hello-1.0.tar.gz", content1, "hello", "1.0",
        set_whitelist=False)
    testapp.patch_json(new_mergeindex.index, [
        'states+=pending',
        'messages+=Please approve'])
    return new_mergeindex


def test_new_merge_index(new_mergeindex, targetindex, testapp):
    r = testapp.get_json(new_mergeindex.index)
    result = r.json['result']
    assert result['type'] == 'merge'
    assert result['acl_upload'] == ['mergeuser']
    assert result['bases'] == [targetindex.stagename]
    assert result['messages'] == ['New push request']
    assert result['states'] == ['new']


def test_submit_merge_index_not_allowed(mapp, new_mergeindex, targetindex, testapp):
    # first turn off push_requests_allowed
    mapp.login(targetindex.stagename.split('/')[0], "123")
    r = testapp.get_json(targetindex.index)
    r = testapp.patch_json(targetindex.index, dict(
        r.json["result"],
        push_requests_allowed=False))
    assert r.json["result"]["push_requests_allowed"] is False
    # now try to submit
    mapp.login(new_mergeindex.stagename.split('/')[0], "123")
    r = testapp.patch_json(new_mergeindex.index, [
        'states+=pending',
        'messages+=Please approve'], expect_errors=True)
    assert r.json["message"] == (
        "The target index '%s' doesn't allow push requests, "
        "The merge index has no packages" % targetindex.stagename)


def test_submit_empty_merge_index(new_mergeindex, targetindex, testapp):
    r = testapp.patch_json(new_mergeindex.index, [
        'states+=pending',
        'messages+=Please approve'], expect_errors=True)
    assert r.json["message"] == "The merge index has no packages"


def test_submit_merge_index(mapp, new_mergeindex, targetindex, testapp):
    content1 = mapp.makepkg("hello-1.0.tar.gz", b"content1", "hello", "1.0")
    mapp.upload_file_pypi(
        "hello-1.0.tar.gz", content1, "hello", "1.0",
        set_whitelist=False)
    r = testapp.patch_json(new_mergeindex.index, [
        'states+=pending',
        'messages+=Please approve'])
    r = testapp.get_json(new_mergeindex.index)
    result = r.json['result']
    assert result['type'] == 'merge'
    assert result['acl_upload'] == ['mergeuser']
    assert result['bases'] == [targetindex.stagename]
    assert result['messages'] == ['New push request', 'Please approve']
    assert result['states'] == ['new', 'pending']


@pytest.mark.parametrize("targetstate", ["approved", "rejected"])
def test_invalid_state_changes_from_new(new_mergeindex, targetstate, testapp):
    r = testapp.patch_json(new_mergeindex.index, [
        'states+=%s' % targetstate,
        'messages+=Change'], expect_errors=True)
    assert r.json["message"] == "State transition from 'new' to '%s' not allowed" % targetstate


def test_approve_pending_not_possible_for_mergeuser(mapp, mergeindex, targetindex, testapp):
    r = testapp.patch_json(mergeindex.index, [
        'states+=approved',
        'messages+=Approve'], expect_errors=True)
    assert r.json["message"] == "user 'mergeuser' cannot upload to '%s'" % targetindex.stagename


def test_approve_pending(mapp, mergeindex, targetindex, testapp):
    # the mergeindex has one project
    r = testapp.get_json(mergeindex.index)
    assert r.json['result']['projects'] == ['hello']
    # the targetindex has no project yet
    r = testapp.get_json(targetindex.index)
    assert r.json['result']['projects'] == []
    # we approve the merge index
    mapp.login(targetindex.stagename.split('/')[0], "123")
    r = testapp.patch_json(mergeindex.index, [
        'states+=approved',
        'messages+=Approve'], expect_errors=True)
    result = r.json['result']
    assert result['type'] == 'merge'
    assert result['acl_upload'] == ['mergeuser']
    assert result['bases'] == [targetindex.stagename]
    assert result['messages'] == ['New push request', 'Please approve', 'Approve']
    assert result['states'] == ['new', 'pending', 'approved']
    # now the targetindex should have the project
    r = testapp.get_json(targetindex.index)
    assert r.json['result']['projects'] == ['hello']
    r = testapp.get_json(targetindex.index + '/hello')
    result = r.json['result']
    assert list(result.keys()) == ['1.0']
    assert result['1.0']['name'] == 'hello'
    assert result['1.0']['version'] == '1.0'
    links = result['1.0']['+links']
    assert len(links) == 1
    assert len(links[0]['log']) == 2
    upload = links[0]['log'][0]
    del upload['when']
    push = links[0]['log'][1]
    del push['when']
    assert upload == {
        'dst': 'mergeuser/+pr-index',
        'what': 'upload',
        'who': 'mergeuser'}
    assert push == {
        'dst': 'targetuser/targetindex',
        'message': 'Approve',
        'src': 'mergeuser/+pr-index',
        'what': 'push',
        'who': 'targetuser'}
    releases = mapp.getreleaseslist('hello', indexname=targetindex.stagename)
    assert releases == [
        'http://localhost/targetuser/targetindex/+f/d0b/425e00e15a0d3/hello-1.0.tar.gz']


def test_reject_pending_not_possible_for_mergeuser(mapp, mergeindex, testapp):
    r = testapp.patch_json(mergeindex.index, [
        'states+=rejected',
        'messages+=Reject'], expect_errors=True)
    assert r.json["message"] == "State transition to 'rejected' not authorized"


def test_cancel_pending(mapp, mergeindex, targetindex, testapp):
    r = testapp.patch_json(mergeindex.index, [
        'states+=new',
        'messages+=Cancel'], expect_errors=True)
    result = r.json['result']
    assert result['type'] == 'merge'
    assert result['acl_upload'] == ['mergeuser']
    assert result['bases'] == [targetindex.stagename]
    assert result['messages'] == ['New push request', 'Please approve', 'Cancel']
    assert result['states'] == ['new', 'pending', 'new']


def test_pr_list(mapp, new_mergeindex, targetindex, testapp):
    r = testapp.get_json(targetindex.index + "/+pr-list")
    result = r.json['result']
    assert result == {'new': {'mergeuser': [['index', 5]]}}
    content1 = mapp.makepkg("hello-1.0.tar.gz", b"content1", "hello", "1.0")
    mapp.upload_file_pypi(
        "hello-1.0.tar.gz", content1, "hello", "1.0",
        set_whitelist=False)
    r = testapp.patch_json(new_mergeindex.index, [
        'states+=pending',
        'messages+=Please approve'])
    r = testapp.get_json(targetindex.index + "/+pr-list")
    result = r.json['result']
    assert result == {'pending': {'mergeuser': [['index', 8]]}}


def test_pr_list_serial(mapp, new_mergeindex, targetindex, testapp):
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
    r = testapp.patch_json(new_mergeindex.index, [
        'states+=pending',
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
