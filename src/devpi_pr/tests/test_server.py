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
def new_prindex(mapp, targetindex):
    mapp.create_and_login_user("pruser")
    api = mapp.create_index(
        "index",
        indexconfig=dict(
            type="pr",
            states="new",
            messages="New push request",
            bases=[targetindex.stagename]))
    return api


@pytest.fixture
def prindex(mapp, new_prindex, targetindex, testapp):
    content1 = mapp.makepkg("pkg-1.0.tar.gz", b"content1", "pkg", "1.0")
    mapp.upload_file_pypi(
        "pkg-1.0.tar.gz", content1, "pkg", "1.0",
        set_whitelist=False)
    testapp.patch_json(new_prindex.index, [
        'states+=pending',
        'messages+=Please approve'])
    return new_prindex


def test_new_pr_index(new_prindex, targetindex, testapp):
    r = testapp.get_json(new_prindex.index)
    result = r.json['result']
    assert result['type'] == 'pr'
    assert result['acl_upload'] == ['pruser']
    assert result['bases'] == [targetindex.stagename]
    assert result['messages'] == ['New push request']
    assert result['states'] == ['new']


def test_submit_pr_index_not_allowed(mapp, new_prindex, targetindex, testapp):
    # first turn off push_requests_allowed
    mapp.login(targetindex.stagename.split('/')[0], "123")
    r = testapp.get_json(targetindex.index)
    r = testapp.patch_json(targetindex.index, dict(
        r.json["result"],
        push_requests_allowed=False))
    assert r.json["result"]["push_requests_allowed"] is False
    # now try to submit
    mapp.login(new_prindex.stagename.split('/')[0], "123")
    r = testapp.patch_json(new_prindex.index, [
        'states+=pending',
        'messages+=Please approve'], expect_errors=True)
    assert r.json["message"] == (
        "The target index '%s' doesn't allow push requests, "
        "The pr index has no packages" % targetindex.stagename)


def test_submit_empty_pr_index(new_prindex, targetindex, testapp):
    r = testapp.patch_json(new_prindex.index, [
        'states+=pending',
        'messages+=Please approve'], expect_errors=True)
    assert r.json["message"] == "The pr index has no packages"


def test_submit_pr_index(mapp, new_prindex, targetindex, testapp):
    content1 = mapp.makepkg("pkg-1.0.tar.gz", b"content1", "pkg", "1.0")
    mapp.upload_file_pypi(
        "pkg-1.0.tar.gz", content1, "pkg", "1.0",
        set_whitelist=False)
    r = testapp.patch_json(new_prindex.index, [
        'states+=pending',
        'messages+=Please approve'])
    r = testapp.get_json(new_prindex.index)
    result = r.json['result']
    assert result['type'] == 'pr'
    assert result['acl_upload'] == ['pruser']
    assert result['bases'] == [targetindex.stagename]
    assert result['messages'] == ['New push request', 'Please approve']
    assert result['states'] == ['new', 'pending']


@pytest.mark.parametrize("targetstate", ["approved", "rejected"])
def test_invalid_state_changes_from_new(new_prindex, targetstate, testapp):
    r = testapp.patch_json(new_prindex.index, [
        'states+=%s' % targetstate,
        'messages+=Change'], expect_errors=True)
    assert r.json["message"] == "State transition from 'new' to '%s' not allowed" % targetstate


def test_approve_pending_not_possible_for_pruser(mapp, prindex, targetindex, testapp):
    headers = {'X-Devpi-PR-Serial': '8'}
    r = testapp.patch_json(prindex.index, [
        'states+=approved',
        'messages+=Approve'], headers=headers, expect_errors=True)
    assert r.json["message"] == "user 'pruser' cannot upload to '%s'" % targetindex.stagename


def test_approve_pending(mapp, prindex, targetindex, testapp):
    # the prindex has one project
    r = testapp.get_json(prindex.index)
    assert r.json['result']['projects'] == ['pkg']
    # the targetindex has no project yet
    r = testapp.get_json(targetindex.index)
    assert r.json['result']['projects'] == []
    # we approve the pr index
    mapp.login(targetindex.stagename.split('/')[0], "123")
    headers = {'X-Devpi-PR-Serial': '8'}
    r = testapp.patch_json(prindex.index, [
        'states+=approved',
        'messages+=Approve'], headers=headers)
    result = r.json['result']
    assert result['type'] == 'pr'
    assert result['acl_upload'] == ['pruser']
    assert result['bases'] == [targetindex.stagename]
    assert result['messages'] == ['New push request', 'Please approve', 'Approve']
    assert result['states'] == ['new', 'pending', 'approved']
    # now the targetindex should have the project
    r = testapp.get_json(targetindex.index)
    assert r.json['result']['projects'] == ['pkg']
    r = testapp.get_json(targetindex.index + '/pkg')
    result = r.json['result']
    assert list(result.keys()) == ['1.0']
    assert result['1.0']['name'] == 'pkg'
    assert result['1.0']['version'] == '1.0'
    links = result['1.0']['+links']
    assert len(links) == 1
    assert len(links[0]['log']) == 2
    upload = links[0]['log'][0]
    del upload['when']
    push = links[0]['log'][1]
    del push['when']
    assert upload == {
        'dst': 'pruser/index',
        'what': 'upload',
        'who': 'pruser'}
    assert push == {
        'dst': 'targetuser/targetindex',
        'message': 'Approve',
        'src': 'pruser/index',
        'what': 'push',
        'who': 'targetuser'}
    releases = mapp.getreleaseslist('pkg', indexname=targetindex.stagename)
    assert releases == [
        'http://localhost/targetuser/targetindex/+f/d0b/425e00e15a0d3/pkg-1.0.tar.gz']


def test_approve_with_toxresult_and_docs(mapp, prindex, targetindex, testapp):
    # the prindex has one project
    r = testapp.get_json(prindex.index)
    assert r.json['result']['projects'] == ['pkg']
    # upload toxresult
    (release_path,) = mapp.get_release_paths('pkg')
    mapp.upload_toxresult(release_path, b"{}")
    # upload doc
    mapp.upload_doc("pkg.doc.zip", b"foo", "pkg", "")
    # the targetindex has no project yet
    r = testapp.get_json(targetindex.index)
    assert r.json['result']['projects'] == []
    # we approve the pr index
    mapp.login(targetindex.stagename.split('/')[0], "123")
    headers = {'X-Devpi-PR-Serial': '10'}
    r = testapp.patch_json(prindex.index, [
        'states+=approved',
        'messages+=Approve'], headers=headers)
    result = r.json['result']
    assert result['type'] == 'pr'
    assert result['acl_upload'] == ['pruser']
    assert result['bases'] == [targetindex.stagename]
    assert result['messages'] == ['New push request', 'Please approve', 'Approve']
    assert result['states'] == ['new', 'pending', 'approved']
    # now the targetindex should have the project
    r = testapp.get_json(targetindex.index)
    assert r.json['result']['projects'] == ['pkg']
    r = testapp.get_json(targetindex.index + '/pkg')
    result = r.json['result']
    assert list(result.keys()) == ['1.0']
    assert result['1.0']['name'] == 'pkg'
    assert result['1.0']['version'] == '1.0'
    links = result['1.0']['+links']
    (release_link,) = [x for x in links if x['rel'] == 'releasefile']
    (toxresult_link,) = [x for x in links if x['rel'] == 'toxresult']
    assert release_link['href'] == toxresult_link['for_href']
    for link in links:
        assert len(link['log']) == 2
        upload = link['log'][0]
        del upload['when']
        push = link['log'][1]
        del push['when']
        assert upload == {
            'dst': 'pruser/index',
            'what': 'upload',
            'who': 'pruser'}
        assert push == {
            'dst': 'targetuser/targetindex',
            'message': 'Approve',
            'src': 'pruser/index',
            'what': 'push',
            'who': 'targetuser'}
    releases = mapp.getreleaseslist('pkg', indexname=targetindex.stagename)
    assert sorted(releases) == [
        'http://localhost/targetuser/targetindex/+f/2c2/6b46b68ffc68f/pkg-1.0.doc.zip',
        'http://localhost/targetuser/targetindex/+f/d0b/425e00e15a0d3/pkg-1.0.tar.gz',
        'http://localhost/targetuser/targetindex/+f/d0b/425e00e15a0d3/pkg-1.0.tar.gz.toxresult0']


def test_reject_pending_not_possible_for_pruser(mapp, prindex, testapp):
    r = testapp.patch_json(prindex.index, [
        'states+=rejected',
        'messages+=Reject'], expect_errors=True)
    assert r.json["message"] == "State transition to 'rejected' not authorized"


def test_cancel_pending(mapp, prindex, targetindex, testapp):
    r = testapp.patch_json(prindex.index, [
        'states+=new',
        'messages+=Cancel'])
    result = r.json['result']
    assert result['type'] == 'pr'
    assert result['acl_upload'] == ['pruser']
    assert result['bases'] == [targetindex.stagename]
    assert result['messages'] == ['New push request', 'Please approve', 'Cancel']
    assert result['states'] == ['new', 'pending', 'new']


def test_approve_already_approved(mapp, prindex, targetindex, testapp):
    # the prindex has one project
    r = testapp.get_json(prindex.index)
    assert r.json['result']['projects'] == ['pkg']
    # the targetindex has no project yet
    r = testapp.get_json(targetindex.index)
    assert r.json['result']['projects'] == []
    # we approve the pr index
    mapp.login(targetindex.stagename.split('/')[0], "123")
    headers = {'X-Devpi-PR-Serial': '8'}
    r = testapp.patch_json(prindex.index, [
        'states+=approved',
        'messages+=Approve'], headers=headers)
    result = r.json['result']
    assert result['type'] == 'pr'
    assert result['acl_upload'] == ['pruser']
    assert result['bases'] == [targetindex.stagename]
    assert result['messages'] == ['New push request', 'Please approve', 'Approve']
    assert result['states'] == ['new', 'pending', 'approved']
    # we try it again
    headers = {'X-Devpi-PR-Serial': '9'}
    r = testapp.patch_json(prindex.index, [
        'states+=approved',
        'messages+=Approve'], headers=headers, expect_errors=True)
    assert r.status_code == 403


def test_approve_wrong_serial(mapp, prindex, targetindex, testapp):
    # the prindex has one project
    r = testapp.get_json(prindex.index)
    assert r.json['result']['projects'] == ['pkg']
    # the targetindex has no project yet
    r = testapp.get_json(targetindex.index)
    assert r.json['result']['projects'] == []
    # we approve the pr index
    mapp.login(targetindex.stagename.split('/')[0], "123")
    headers = {'X-Devpi-PR-Serial': '1'}
    r = testapp.patch_json(prindex.index, [
        'states+=approved',
        'messages+=Approve'], headers=headers, expect_errors=True)
    assert r.json["message"] == "got X-Devpi-PR-Serial 1, expected 8"
    r = testapp.get_json(prindex.index)
    result = r.json['result']
    assert result['type'] == 'pr'
    assert result['acl_upload'] == ['pruser']
    assert result['bases'] == [targetindex.stagename]
    assert result['messages'] == ['New push request', 'Please approve']
    assert result['states'] == ['new', 'pending']


def test_approve_nonvolatile_conflict(mapp, prindex, targetindex, testapp):
    # make target index non volatile
    mapp.login(targetindex.stagename.split('/')[0], "123")
    testapp.patch_json(targetindex.index, ['volatile=False'])
    # the prindex has one project
    r = testapp.get_json(prindex.index)
    assert r.json['result']['projects'] == ['pkg']
    # the targetindex has no project yet
    r = testapp.get_json(targetindex.index)
    assert r.json['result']['projects'] == []
    # the targetindex is actually non volatile
    assert r.json['result']['volatile'] is False
    # we approve the pr index
    headers = {'X-Devpi-PR-Serial': '8'}
    r = testapp.patch_json(prindex.index, [
        'states+=approved',
        'messages+=Approve'], headers=headers)
    # now the targetindex should have the project
    r = testapp.get_json(targetindex.index)
    assert r.json['result']['projects'] == ['pkg']
    # create another pr index with conflicting pkg
    mapp.login(prindex.stagename.split('/')[0], "123")
    otherprindex = mapp.create_index(
        "other",
        indexconfig=dict(
            type="pr",
            states="new",
            messages="New push request",
            bases=[targetindex.stagename]))
    content1 = mapp.makepkg("pkg-1.0.tar.gz", b"content1", "pkg", "1.0")
    mapp.upload_file_pypi(
        "pkg-1.0.tar.gz", content1, "pkg", "1.0",
        set_whitelist=False)
    r = testapp.patch_json(otherprindex.index, [
        'states+=pending',
        'messages+=Please approve'])
    serial = r.headers['X-Devpi-Serial']
    headers = {'X-Devpi-PR-Serial': serial}
    mapp.login(targetindex.stagename.split('/')[0], "123")
    r = testapp.patch_json(otherprindex.index, [
        'states+=approved',
        'messages+=Approve'], headers=headers, expect_errors=True)
    assert r.status_code == 409
    assert r.json['message'] == "pkg-1.0.tar.gz already exists in non-volatile index"


def test_pr_list(mapp, new_prindex, targetindex, testapp):
    r = testapp.get_json(targetindex.index + "/+pr-list")
    result = r.json['result']
    assert result == {'new': {'pruser': [{
        'name': 'index',
        'base': 'targetuser/targetindex',
        'last_serial': 5,
        'by': ['pruser'],
        'states': ['new'],
        'messages': ['New push request']}]}}
    r = testapp.get_json(new_prindex.index + "/+pr-list")
    result = r.json['result']
    assert result == {'new': {'pruser': [{
        'name': 'index',
        'base': 'targetuser/targetindex',
        'last_serial': 5,
        'by': ['pruser'],
        'states': ['new'],
        'messages': ['New push request']}]}}
    r = testapp.get_json("/pruser/+pr-list")
    result = r.json['result']
    assert result == {'new': {'pruser': [{
        'name': 'index',
        'base': 'targetuser/targetindex',
        'last_serial': 5,
        'by': ['pruser'],
        'states': ['new'],
        'messages': ['New push request']}]}}
    content1 = mapp.makepkg("pkg-1.0.tar.gz", b"content1", "pkg", "1.0")
    mapp.upload_file_pypi(
        "pkg-1.0.tar.gz", content1, "pkg", "1.0",
        set_whitelist=False)
    r = testapp.patch_json(new_prindex.index, [
        'states+=pending',
        'messages+=Please approve'])
    r = testapp.get_json(targetindex.index + "/+pr-list")
    result = r.json['result']
    assert result == {'pending': {'pruser': [{
        'name': 'index',
        'base': 'targetuser/targetindex',
        'last_serial': 8,
        'by': ['pruser', 'pruser'],
        'states': ['new', 'pending'],
        'messages': ['New push request', 'Please approve']}]}}
    r = testapp.get_json("/pruser/+pr-list")
    result = r.json['result']
    assert result == {'pending': {'pruser': [{
        'name': 'index',
        'base': 'targetuser/targetindex',
        'last_serial': 8,
        'by': ['pruser', 'pruser'],
        'states': ['new', 'pending'],
        'messages': ['New push request', 'Please approve']}]}}


def test_pr_list_serial(mapp, new_prindex, targetindex, testapp):
    r = testapp.get_json(targetindex.index + "/+pr-list")
    result = r.json['result']
    assert result == {'new': {'pruser': [{
        'name': 'index',
        'base': 'targetuser/targetindex',
        'last_serial': 5,
        'by': ['pruser'],
        'states': ['new'],
        'messages': ['New push request']}]}}
    content1 = mapp.makepkg("pkg-1.0.tar.gz", b"content1", "pkg", "1.0")
    mapp.upload_file_pypi(
        "pkg-1.0.tar.gz", content1, "pkg", "1.0",
        set_whitelist=False)
    r = testapp.get_json(targetindex.index + "/+pr-list")
    result = r.json['result']
    # serial 6 is registration, serial 7 is the upload
    assert result == {'new': {'pruser': [{
        'name': 'index',
        'base': 'targetuser/targetindex',
        'last_serial': 7,
        'by': ['pruser'],
        'states': ['new'],
        'messages': ['New push request']}]}}
    r = testapp.patch_json(new_prindex.index, [
        'states+=pending',
        'messages+=Please approve'])
    r = testapp.get_json(targetindex.index + "/+pr-list")
    result = r.json['result']
    # serial 8 is submit
    assert result == {'pending': {'pruser': [{
        'name': 'index',
        'base': 'targetuser/targetindex',
        'last_serial': 8,
        'by': ['pruser', 'pruser'],
        'states': ['new', 'pending'],
        'messages': ['New push request', 'Please approve']}]}}
    content2 = mapp.makepkg("pkg-1.0.zip", b"content2", "pkg", "1.0")
    mapp.upload_file_pypi(
        "pkg-1.0.zip", content2, "pkg", "1.0",
        set_whitelist=False)
    r = testapp.get_json(targetindex.index + "/+pr-list")
    result = r.json['result']
    # serial 9 is second upload
    assert result == {'pending': {'pruser': [{
        'name': 'index',
        'base': 'targetuser/targetindex',
        'last_serial': 9,
        'by': ['pruser', 'pruser'],
        'states': ['new', 'pending'],
        'messages': ['New push request', 'Please approve']}]}}
    mapp.create_index(
        "other",
        indexconfig=dict(
            type="pr",
            states="new",
            messages="Different push request",
            bases=[targetindex.stagename]))
    r = testapp.get_json(targetindex.index + "/+pr-list")
    result = r.json['result']
    # serial 10 is the new pr index, the old index should still be at 9
    assert result == {
        'pending': {'pruser': [{
            'name': 'index',
            'base': 'targetuser/targetindex',
            'last_serial': 9,
            'by': ['pruser', 'pruser'],
            'states': ['new', 'pending'],
            'messages': ['New push request', 'Please approve']}]},
        'new': {'pruser': [{
            'name': 'other',
            'base': 'targetuser/targetindex',
            'last_serial': 10,
            'by': ['pruser'],
            'states': ['new'],
            'messages': ['Different push request']}]}}
    # we register another project
    mapp.use("pruser/index")
    mapp.set_versiondata(dict(name="hello", version="1.0"), set_whitelist=False)
    r = testapp.get_json(targetindex.index + "/+pr-list")
    result = r.json['result']
    # that should be serial 11
    assert result == {
        'pending': {'pruser': [{
            'name': 'index',
            'base': 'targetuser/targetindex',
            'last_serial': 11,
            'by': ['pruser', 'pruser'],
            'states': ['new', 'pending'],
            'messages': ['New push request', 'Please approve']}]},
        'new': {'pruser': [{
            'name': 'other',
            'base': 'targetuser/targetindex',
            'last_serial': 10,
            'by': ['pruser'],
            'states': ['new'],
            'messages': ['Different push request']}]}}
    # now we delete a project
    mapp.delete_project("pkg")
    r = testapp.get_json(targetindex.index + "/+pr-list")
    result = r.json['result']
    # the deletion should be 12
    assert result == {
        'pending': {'pruser': [{
            'name': 'index',
            'base': 'targetuser/targetindex',
            'last_serial': 12,
            'by': ['pruser', 'pruser'],
            'states': ['new', 'pending'],
            'messages': ['New push request', 'Please approve']}]},
        'new': {'pruser': [{
            'name': 'other',
            'base': 'targetuser/targetindex',
            'last_serial': 10,
            'by': ['pruser'],
            'states': ['new'],
            'messages': ['Different push request']}]}}


def test_pr_list_approved(mapp, new_prindex, targetindex, testapp):
    content1 = mapp.makepkg("pkg-1.0.tar.gz", b"content1", "pkg", "1.0")
    mapp.upload_file_pypi(
        "pkg-1.0.tar.gz", content1, "pkg", "1.0",
        set_whitelist=False)
    r = testapp.patch_json(new_prindex.index, [
        'states+=pending',
        'messages+=Please approve'])
    r = testapp.get_json(targetindex.index + "/+pr-list")
    result = r.json['result']
    assert result == {'pending': {'pruser': [{
        'name': 'index',
        'base': 'targetuser/targetindex',
        'last_serial': 8,
        'by': ['pruser', 'pruser'],
        'states': ['new', 'pending'],
        'messages': ['New push request', 'Please approve']}]}}
    r = testapp.get_json("/pruser/+pr-list")
    result = r.json['result']
    assert result == {'pending': {'pruser': [{
        'name': 'index',
        'base': 'targetuser/targetindex',
        'last_serial': 8,
        'by': ['pruser', 'pruser'],
        'states': ['new', 'pending'],
        'messages': ['New push request', 'Please approve']}]}}
    # we approve the pr index
    mapp.login(targetindex.stagename.split('/')[0], "123")
    headers = {'X-Devpi-PR-Serial': '8'}
    r = testapp.patch_json(new_prindex.index, [
        'states+=approved',
        'messages+=Approve'], headers=headers)
    r = testapp.get_json(targetindex.index + "/+pr-list")
    result = r.json['result']
    assert result == {'approved': {'pruser': [{
        'name': 'index',
        'base': 'targetuser/targetindex',
        'last_serial': 9,
        'by': ['pruser', 'pruser', 'targetuser'],
        'states': ['new', 'pending', 'approved'],
        'messages': ['New push request', 'Please approve', 'Approve']}]}}
    r = testapp.get_json("/pruser/+pr-list")
    result = r.json['result']
    assert result == {'approved': {'pruser': [{
        'name': 'index',
        'base': 'targetuser/targetindex',
        'last_serial': 9,
        'by': ['pruser', 'pruser', 'targetuser'],
        'states': ['new', 'pending', 'approved'],
        'messages': ['New push request', 'Please approve', 'Approve']}]}}
