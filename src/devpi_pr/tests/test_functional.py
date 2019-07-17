import pytest
import re
try:
    from devpi_server import __version__  # noqa
except ImportError:
    pytestmark = pytest.mark.skip("No devpi-server installed")
try:
    from devpi import __version__  # noqa
except ImportError:
    pytestmark = pytest.mark.skip("No devpi-client installed")


@pytest.fixture(autouse=True)
def devpi_pr_data_dir(monkeypatch, tmpdir):
    path = tmpdir.join('devpi-pr-user-data').ensure_dir()
    monkeypatch.setattr("devpi_pr.client.devpi_pr_data_dir", path.strpath)
    yield path


@pytest.fixture
def get_review_json(devpi_pr_data_dir):
    import json

    def get_review_json():
        return json.loads(
            devpi_pr_data_dir.join("reviews.json").read_text("utf-8"))

    return get_review_json


def test_manual_index_creation(capfd, devpi, getjson, makepkg):
    devpi(
        "index", "-c",
        "manual",
        "type=pr",
        "states=new",
        "messages=New pull request",
        "bases=%s/dev" % devpi.target,
        code=200)
    (out, err) = capfd.readouterr()
    data = getjson("manual")["result"]
    assert data["type"] == "pr"
    assert data["states"] == ["new"]
    assert data["messages"] == ["New pull request"]
    pkg = makepkg("hello-1.0.tar.gz", b"content1", "hello", "1.0")
    devpi(
        "upload",
        "--index", "manual",
        pkg.strpath)
    devpi(
        "index",
        "manual",
        "states+=pending",
        "messages+=Please accept these updated packages",
        code=200)
    (out, err) = capfd.readouterr()
    data = getjson("manual")["result"]
    assert data["states"] == ["new", "pending"]
    assert data["messages"] == [
        "New pull request",
        "Please accept these updated packages"]


def test_index_creation(capfd, devpi, getjson, makepkg):
    devpi(
        "new-pr",
        "20180717",
        "%s/dev" % devpi.target,
        code=200)
    (out, err) = capfd.readouterr()
    data = getjson("20180717")["result"]
    assert data["type"] == "pr"
    assert data["states"] == ["new"]
    assert data["messages"] == ["New pull request"]
    pkg = makepkg("hello-1.0.tar.gz", b"content1", "hello", "1.0")
    devpi(
        "upload",
        "--index", "20180717",
        pkg.strpath)
    devpi(
        "submit-pr",
        "20180717",
        "-m", "Please accept these updated packages",
        code=200)
    (out, err) = capfd.readouterr()
    data = getjson("20180717")["result"]
    assert data["states"] == ["new", "pending"]
    assert data["messages"] == [
        "New pull request",
        "Please accept these updated packages"]


@pytest.mark.parametrize(
    "keep_index", (True, False),
    ids=["with_keep_index", "without_keep_index"])
@pytest.mark.parametrize(
    "use_review_cmd", (True, False),
    ids=["using_review_pr", "using_serial_arg"])
def test_approval(capfd, devpi, get_review_json, getjson, keep_index, makepkg, use_review_cmd):
    devpi(
        "new-pr",
        "20180717",
        "%s/dev" % devpi.target,
        code=200)
    pkg = makepkg("hello-1.0.tar.gz", b"content1", "hello", "1.0")
    devpi(
        "upload",
        "--index", "20180717",
        pkg.strpath)
    devpi(
        "submit-pr",
        "20180717",
        "-m", "Please accept these updated packages",
        code=200)
    data = getjson("dev")["result"]
    assert data['projects'] == []
    # login as target user
    devpi("login", devpi.target, "--password", "123")
    devpi("use", "dev")
    (out, err) = capfd.readouterr()
    devpi(
        "list-prs",
        code=200)
    (out, err) = capfd.readouterr()
    lines = out.splitlines()
    assert 'pending pull requests' in lines[-2]
    if use_review_cmd:
        devpi(
            "review-pr",
            "%s/20180717" % devpi.user,
            code=200)
        (out, err) = capfd.readouterr()
        assert "Started review of '%s/20180717' at serial" % devpi.user in out
        assert list(get_review_json()) == ['%s/20180717' % devpi.user]
    else:
        serial = lines[-1].split()[-1]
    args = [
        "approve-pr",
        "%s/20180717" % devpi.user,
        "-m", "The pull request was accepted"]
    if not use_review_cmd:
        args.extend(["--serial", serial])
    if keep_index:
        args.append('--keep-index')
        devpi(*args, code=200)
        data = getjson("20180717")["result"]
        assert data["states"] == ["new", "pending", "approved"]
        assert data["messages"] == [
            "New pull request",
            "Please accept these updated packages",
            "The pull request was accepted"]
    else:
        devpi(*args, code=201)
    if use_review_cmd:
        assert get_review_json() == {}
    data = getjson("%s/dev" % devpi.target)["result"]
    assert data['projects'] == ['hello']
    data = getjson("%s/dev/hello" % devpi.target)["result"]
    assert list(data.keys()) == ['1.0']
    assert data['1.0']['name'] == 'hello'
    assert data['1.0']['version'] == '1.0'
    links = data['1.0']['+links']
    assert len(links) == 1
    assert len(links[0]['log']) == 2
    upload = links[0]['log'][0]
    del upload['when']
    push = links[0]['log'][1]
    del push['when']
    assert upload == {
        'dst': '%s/20180717' % devpi.user,
        'what': 'upload',
        'who': '%s' % devpi.user}
    assert push == {
        'dst': '%s/dev' % devpi.target,
        'message': 'The pull request was accepted',
        'src': '%s/20180717' % devpi.user,
        'what': 'push',
        'who': '%s' % devpi.target}


def test_abort_review(capfd, devpi, get_review_json, makepkg):
    devpi(
        "new-pr",
        "20190528",
        "%s/dev" % devpi.target,
        code=200)
    pkg = makepkg("foo-1.0.tar.gz", b"content1", "foo", "1.0")
    devpi(
        "upload",
        "--index", "20190528",
        pkg.strpath)
    devpi(
        "submit-pr",
        "20190528",
        "-m", "Please accept these updated packages",
        code=200)
    # login as target user
    devpi("login", devpi.target, "--password", "123")
    devpi("use", "dev")
    devpi(
        "review-pr",
        "%s/20190528" % devpi.user,
        code=200)
    (out, err) = capfd.readouterr()
    assert "Started review of '%s/20190528' at serial" % devpi.user in out
    assert list(get_review_json()) == ['%s/20190528' % devpi.user]
    devpi(
        "abort-pr-review",
        "%s/20190528" % devpi.user)
    (out, err) = capfd.readouterr()
    assert "Aborted review of '%s/20190528'" % devpi.user in out
    assert get_review_json() == {}
    devpi(
        "abort-pr-review",
        "%s/20190528" % devpi.user)
    (out, err) = capfd.readouterr()
    assert "No review of '%s/20190528' active" % devpi.user in out


def test_double_review(capfd, devpi, get_review_json, makepkg):
    devpi(
        "new-pr",
        "20190527",
        "%s/dev" % devpi.target,
        code=200)
    pkg = makepkg("foo-1.0.tar.gz", b"content1", "foo", "1.0")
    devpi(
        "upload",
        "--index", "20190527",
        pkg.strpath)
    devpi(
        "submit-pr",
        "20190527",
        "-m", "Please accept these updated packages",
        code=200)
    # login as target user
    devpi("login", devpi.target, "--password", "123")
    devpi("use", "dev")
    devpi(
        "review-pr",
        "%s/20190527" % devpi.user,
        code=200)
    (out, err) = capfd.readouterr()
    assert "Started review of '%s/20190527' at serial" % devpi.user in out
    first_serial = get_review_json()['%s/20190527' % devpi.user]
    devpi(
        "review-pr",
        "%s/20190527" % devpi.user,
        code=200)
    (out, err) = capfd.readouterr()
    assert "Already reviewing '%s/20190527' at serial" % devpi.user in out
    second_serial = get_review_json()['%s/20190527' % devpi.user]
    assert first_serial == second_serial


def test_review_update(capfd, devpi, get_review_json, getjson, makepkg):
    devpi(
        "new-pr",
        "20190529",
        "%s/dev" % devpi.target,
        code=200)
    pkg = makepkg("hello-1.0.tar.gz", b"content1", "hello", "1.0")
    devpi(
        "upload",
        "--index", "20190529",
        pkg.strpath)
    devpi(
        "submit-pr",
        "20190529",
        "-m", "Please accept these updated packages",
        code=200)
    # login as target user
    devpi("login", devpi.target, "--password", "123")
    devpi("use", "dev")
    (out, err) = capfd.readouterr()
    devpi(
        "list-prs",
        code=200)
    (out, err) = capfd.readouterr()
    devpi(
        "review-pr",
        "%s/20190529" % devpi.user,
        code=200)
    (out, err) = capfd.readouterr()
    assert "Started review of '%s/20190529' at serial" % devpi.user in out
    assert list(get_review_json()) == ['%s/20190529' % devpi.user]
    first_serial = get_review_json()['%s/20190529' % devpi.user]
    # login back in as source user
    devpi("login", devpi.user, "--password", "123")
    pkg2 = makepkg("pkg-1.0.tar.gz", b"content2", "pkg", "1.0")
    devpi(
        "upload",
        "--index", "20190529",
        pkg2.strpath)
    # and login again as target user
    devpi("login", devpi.target, "--password", "123")
    devpi("use", "dev")
    (out, err) = capfd.readouterr()
    devpi(
        "approve-pr",
        "%s/20190529" % devpi.user,
        "-m", "The pull request was accepted",
        code=400)
    (out, err) = capfd.readouterr()
    m = re.search(r'x-devpi-pr-serial (\d+), expected (\d+)', out, re.IGNORECASE)
    got_serial = int(m.group(1))
    expected_serial = int(m.group(2))
    assert expected_serial > got_serial
    devpi(
        "review-pr",
        "%s/20190529" % devpi.user,
        "--update",
        code=200)
    (out, err) = capfd.readouterr()
    assert "Updated review of '%s/20190529' to serial %s" % (
        devpi.user, expected_serial) in out
    assert list(get_review_json()) == ['%s/20190529' % devpi.user]
    second_serial = get_review_json()['%s/20190529' % devpi.user]
    assert int(second_serial) > int(first_serial)
    devpi(
        "approve-pr",
        "%s/20190529" % devpi.user,
        "-m", "The pull request was accepted",
        code=201)
    data = getjson("%s/dev" % devpi.target)["result"]
    assert data['projects'] == ['hello', 'pkg']


def test_add_on_create(capfd, devpi, getjson, makepkg):
    pkg = makepkg("hello-1.0.tar.gz", b"content1", "hello", "1.0")
    devpi(
        "upload",
        "--index", "dev",
        pkg.strpath)
    devpi(
        "new-pr",
        "20190128",
        "%s/dev" % devpi.target,
        "hello==1.0",
        code=200)
    # clear output
    capfd.readouterr()
    devpi(
        "list-prs",
        "%s/20190128" % devpi.user,
        code=200)
    (out, err) = capfd.readouterr()
    lines = list(x.strip() for x in out.splitlines()[-2:])
    assert lines[0] == "new pull requests"
    assert lines[1].startswith(
        "%s/20190128 -> %s/dev" % (devpi.user, devpi.target))
    data = getjson("/%s/20190128" % devpi.user)["result"]
    assert data["projects"] == ["hello"]
    data = getjson("/%s/20190128/hello" % devpi.user)["result"]
    assert list(data.keys()) == ["1.0"]
    (link,) = data["1.0"]["+links"]
    assert "hello-1.0.tar.gz" in link["href"]


def test_reject(capfd, devpi, getjson, makepkg):
    pkg = makepkg("hello-1.0.tar.gz", b"content1", "hello", "1.0")
    devpi(
        "upload",
        "--index", "dev",
        pkg.strpath)
    devpi(
        "new-pr",
        "20190128",
        "%s/dev" % devpi.target,
        "hello==1.0",
        code=200)
    devpi(
        "submit-pr",
        "20190128",
        "-m", "Please accept these updated packages",
        code=200)
    # login as target user
    devpi("login", devpi.target, "--password", "123")
    devpi("use", "dev")
    devpi(
        "reject-pr",
        "%s/20190128" % devpi.user,
        "-m", "The pull request was rejected",
        code=200)
    # clear output
    capfd.readouterr()
    devpi(
        "list-prs",
        code=200)
    (out, err) = capfd.readouterr()
    lines = list(x.strip() for x in out.splitlines()[-2:])
    assert lines[0] == "rejected pull requests"
    assert lines[1].startswith(
        "%s/20190128 -> %s/dev" % (devpi.user, devpi.target))
    data = getjson("20190128")["result"]
    assert data["states"] == ["new", "pending", "rejected"]
    assert data["messages"] == [
        "New pull request",
        "Please accept these updated packages",
        "The pull request was rejected"]
    data = getjson("%s/dev" % devpi.target)["result"]
    assert data['projects'] == []
    # login as pull request user
    devpi("login", devpi.user, "--password", "123")
    devpi("use", "dev")
    # submit again
    devpi(
        "submit-pr",
        "20190128",
        "-m", "Please accept these fixed packages",
        code=200)
    data = getjson("20190128")["result"]
    assert data["states"] == ["new", "pending", "rejected", "pending"]
    assert data["messages"] == [
        "New pull request",
        "Please accept these updated packages",
        "The pull request was rejected",
        "Please accept these fixed packages"]
    data = getjson("%s/dev" % devpi.target)["result"]
    assert data['projects'] == []


def test_cancel(capfd, devpi, getjson, makepkg):
    pkg = makepkg("hello-1.0.tar.gz", b"content1", "hello", "1.0")
    devpi(
        "upload",
        "--index", "dev",
        pkg.strpath)
    devpi(
        "new-pr",
        "20190128",
        "%s/dev" % devpi.target,
        "hello==1.0",
        code=200)
    devpi(
        "submit-pr",
        "20190128",
        "-m", "Please accept these updated packages",
        code=200)
    devpi(
        "cancel-pr",
        "20190128",
        "-m", "Never mind",
        code=200)
    # clear output
    capfd.readouterr()
    devpi(
        "list-prs", "-a",
        code=200)
    (out, err) = capfd.readouterr()
    lines = list(x.strip() for x in out.splitlines()[-2:])
    assert lines[0] == "new pull requests"
    assert lines[1].startswith(
        "%s/20190128 -> %s/dev" % (devpi.user, devpi.target))
    data = getjson("20190128")["result"]
    assert data["states"] == ["new", "pending", "new"]
    assert data["messages"] == [
        "New pull request",
        "Please accept these updated packages",
        "Never mind"]
    data = getjson("%s/dev" % devpi.target)["result"]
    assert data['projects'] == []


def test_delete(capfd, devpi):
    devpi(
        "new-pr",
        "20190128",
        "%s/dev" % devpi.target,
        code=200)
    # clear output
    capfd.readouterr()
    devpi(
        "list-prs", "--all-states",
        code=200)
    (out, err) = capfd.readouterr()
    lines = list(x.strip() for x in out.splitlines()[-2:])
    assert lines[0] == "new pull requests"
    assert lines[1].startswith(
        "%s/20190128 -> %s/dev" % (devpi.user, devpi.target))
    devpi(
        "delete-pr",
        "20190128",
        code=201)
    capfd.readouterr()
    devpi(
        "list-prs",
        code=200)
    (out, err) = capfd.readouterr()
    assert "20190128" not in out


def test_pr_listing(capfd, devpi, getjson, makepkg):
    # a new one
    devpi(
        "new-pr",
        "20181217",
        "%s/dev" % devpi.target,
        code=200)
    # a submitted one
    devpi(
        "new-pr",
        "20180717",
        "%s/dev" % devpi.target,
        code=200)
    pkg = makepkg("hello-1.0.tar.gz", b"content1", "hello", "1.0")
    devpi(
        "upload",
        "--index", "20180717",
        pkg.strpath)
    devpi(
        "submit-pr",
        "20180717",
        "-m", "Please accept these updated packages",
        code=200)
    # one being reviewed
    devpi(
        "new-pr",
        "20190529",
        "%s/dev" % devpi.target,
        code=200)
    devpi(
        "upload",
        "--index", "20190529",
        pkg.strpath)
    devpi(
        "submit-pr",
        "20190529",
        "-m", "Please review",
        code=200)
    devpi("login", devpi.target, "--password", "123")
    devpi("use", "dev")
    devpi(
        "review-pr",
        "%s/20190529" % devpi.user,
        code=200)
    (out, err) = capfd.readouterr()
    # get the listing
    devpi(
        "list-prs",
        code=200)
    (out, err) = capfd.readouterr()
    assert "new pull requests" not in out
    assert "%s/20181217" % devpi.user not in out
    assert "pending pull requests" in out
    assert "%s/20180717" % devpi.user in out
    assert "%s/20190529" % devpi.user in out
    assert "(reviewing)" in out
    # get the listing with all states
    devpi(
        "list-prs", "-a",
        code=200)
    (out, err) = capfd.readouterr()
    assert "new pull requests" in out
    assert "%s/20181217" % devpi.user in out
    assert "pending pull requests" in out
    assert "%s/20180717" % devpi.user in out
    assert "%s/20190529" % devpi.user in out
    assert "(reviewing)" in out
    # get the listing with all states and messages
    devpi(
        "list-prs", "-m",
        code=200)
    (out, err) = capfd.readouterr()
    assert "new pull requests" not in out
    assert "%s/20181217" % devpi.user not in out
    assert "pending pull requests" in out
    assert "%s/20180717" % devpi.user in out
    assert "%s/20190529" % devpi.user in out
    assert "(reviewing)" in out
    assert "new by %s:" % devpi.user in out
    assert "pending by %s:" % devpi.user in out
    assert "Please accept these updated packages" in out
    assert "Please review" in out


def test_index_not_found(capfd, devpi):
    devpi("approve-pr", "nonexisting", "--serial", "10", "-m", "msg", code=404)
    (out, err) = capfd.readouterr()
    last_line = out.splitlines()[-1].strip()
    assert last_line == "Couldn't access pr index 'nonexisting': Not Found"
    devpi("reject-pr", "nonexisting", "-m", "msg", code=404)
    (out, err) = capfd.readouterr()
    last_line = out.splitlines()[-1].strip()
    assert last_line == "Couldn't access pr index 'nonexisting': Not Found"
    devpi("submit-pr", "nonexisting", "-m", "msg", code=404)
    (out, err) = capfd.readouterr()
    last_line = out.splitlines()[-1].strip()
    assert last_line == "Couldn't access pr index 'nonexisting': Not Found"
    devpi("cancel-pr", "nonexisting", "-m", "msg", code=404)
    (out, err) = capfd.readouterr()
    last_line = out.splitlines()[-1].strip()
    assert last_line == "Couldn't access pr index 'nonexisting': Not Found"
    devpi("delete-pr", "nonexisting", code=404)
    (out, err) = capfd.readouterr()
    last_line = out.splitlines()[-1].strip()
    assert last_line == "Couldn't access pr index 'nonexisting': Not Found"
