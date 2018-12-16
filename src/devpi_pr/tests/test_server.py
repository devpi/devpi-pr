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
        'messages+=Please accept'], expect_errors=True)
    assert r.json["message"] == "The target index '%s' doesn't allow push requests" % targetindex.stagename


def test_submit_merge_index(mergeindex, targetindex, testapp):
    r = testapp.patch_json(mergeindex.index, [
        'state=pending',
        'messages+=Please accept'])
    r = testapp.get_json(mergeindex.index)
    result = r.json['result']
    assert result['type'] == 'merge'
    assert result['acl_upload'] == ['mergeuser']
    assert result['bases'] == [targetindex.stagename]
    assert result['messages'] == ['Please accept']
    assert result['state'] == 'pending'


def test_accept_new_not_possible(mergeindex, testapp):
    r = testapp.patch_json(mergeindex.index, [
        'state=accepted',
        'messages+=Accept'], expect_errors=True)
    assert r.json["message"] == "The merge index isn't in state 'pending'"


def test_reject_new_not_possible(mergeindex, testapp):
    r = testapp.patch_json(mergeindex.index, [
        'state=rejected',
        'messages+=Accept'], expect_errors=True)
    assert r.json["message"] == "The merge index isn't in state 'pending'"
