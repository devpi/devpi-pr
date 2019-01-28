import json
import pytest
try:
    from devpi_server import __version__  # noqa
except ImportError:
    pytestmark = pytest.mark.skip("No devpi-server installed")
try:
    from devpi import __version__  # noqa
except ImportError:
    pytestmark = pytest.mark.skip("No devpi-client installed")


def test_manual_index_creation(capfd, devpi, getjson, makepkg):
    devpi(
        "index", "-c",
        "+pr-manual",
        "type=merge",
        "states=new",
        "messages=New push request",
        "bases=%s/dev" % devpi.target,
        code=200)
    (out, err) = capfd.readouterr()
    data = getjson("+pr-manual")["result"]
    assert data["type"] == "merge"
    assert data["states"] == ["new"]
    assert data["messages"] == ["New push request"]
    pkg = makepkg("hello-1.0.tar.gz", b"content1", "hello", "1.0")
    devpi(
        "upload",
        "--index", "+pr-manual",
        pkg.strpath)
    devpi(
        "index",
        "+pr-manual",
        "states+=pending",
        "messages+=Please accept these updated packages",
        code=200)
    (out, err) = capfd.readouterr()
    data = getjson("+pr-manual")["result"]
    assert data["states"] == ["new", "pending"]
    assert data["messages"] == [
        "New push request",
        "Please accept these updated packages"]


def test_manual_index_creation_invalid_prefix(capfd, devpi):
    devpi(
        "index", "-c",
        "invalid_prefix",
        "type=merge",
        "bases=%s/dev" % devpi.target,
        code=400)
    (out, err) = capfd.readouterr()
    assert "indexname 'invalid_prefix' must start with '+pr-'." in out


def test_manual_index_creation_invalid_name(capfd, devpi):
    devpi(
        "index", "-c",
        "+pr-invalid[name]",
        "type=merge",
        "bases=%s/dev" % devpi.target,
        code=400)
    (out, err) = capfd.readouterr()
    assert "indexname 'invalid[name]' contains characters" in out


def test_index_creation(capfd, devpi, getjson, makepkg):
    devpi(
        "new-pr",
        "20180717",
        "%s/dev" % devpi.target,
        code=200)
    (out, err) = capfd.readouterr()
    data = getjson("+pr-20180717")["result"]
    assert data["type"] == "merge"
    assert data["states"] == ["new"]
    assert data["messages"] == ["New push request"]
    pkg = makepkg("hello-1.0.tar.gz", b"content1", "hello", "1.0")
    devpi(
        "upload",
        "--index", "+pr-20180717",
        pkg.strpath)
    devpi(
        "submit-pr",
        "20180717",
        "-m", "Please accept these updated packages",
        code=200)
    (out, err) = capfd.readouterr()
    data = getjson("+pr-20180717")["result"]
    assert data["states"] == ["new", "pending"]
    assert data["messages"] == [
        "New push request",
        "Please accept these updated packages"]


def test_approval(capfd, devpi, getjson, makepkg):
    devpi(
        "new-pr",
        "20180717",
        "%s/dev" % devpi.target,
        code=200)
    pkg = makepkg("hello-1.0.tar.gz", b"content1", "hello", "1.0")
    devpi(
        "upload",
        "--index", "+pr-20180717",
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
    assert 'pending push requests' in lines[-2]
    serial = lines[-1].split()[-1]
    devpi(
        "approve-pr",
        "%s/20180717" % devpi.user,
        "%s" % serial,
        "-m", "The push request was accepted",
        code=200)
    data = getjson("+pr-20180717")["result"]
    assert data["states"] == ["new", "pending", "approved"]
    assert data["messages"] == [
        "New push request",
        "Please accept these updated packages",
        "The push request was accepted"]
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
        'dst': '%s/+pr-20180717' % devpi.user,
        'what': 'upload',
        'who': '%s' % devpi.user}
    assert push == {
        'dst': '%s/dev' % devpi.target,
        'message': 'The push request was accepted',
        'src': '%s/+pr-20180717' % devpi.user,
        'what': 'push',
        'who': '%s' % devpi.target}


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
        code=200)
    (out, err) = capfd.readouterr()
    lines = list(x.strip() for x in out.splitlines()[-2:])
    assert lines[0] == "new push requests"
    assert lines[1].startswith(
        "%s/20190128 -> %s/dev" % (devpi.user, devpi.target))
    data = getjson("/%s/+pr-20190128" % devpi.user)["result"]
    assert data["projects"] == ["hello"]
    data = getjson("/%s/+pr-20190128/hello" % devpi.user)["result"]
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
        "-m", "The push request was rejected",
        code=200)
    # clear output
    capfd.readouterr()
    devpi(
        "list-prs",
        code=200)
    (out, err) = capfd.readouterr()
    lines = list(x.strip() for x in out.splitlines()[-2:])
    assert lines[0] == "rejected push requests"
    assert lines[1].startswith(
        "%s/20190128 -> %s/dev" % (devpi.user, devpi.target))
    data = getjson("+pr-20190128")["result"]
    assert data["states"] == ["new", "pending", "rejected"]
    assert data["messages"] == [
        "New push request",
        "Please accept these updated packages",
        "The push request was rejected"]
    data = getjson("%s/dev" % devpi.target)["result"]
    assert data['projects'] == []
    # login as push request user
    devpi("login", devpi.user, "--password", "123")
    devpi("use", "dev")
    # submit again
    devpi(
        "submit-pr",
        "20190128",
        "-m", "Please accept these fixed packages",
        code=200)
    data = getjson("+pr-20190128")["result"]
    assert data["states"] == ["new", "pending", "rejected", "pending"]
    assert data["messages"] == [
        "New push request",
        "Please accept these updated packages",
        "The push request was rejected",
        "Please accept these fixed packages"]
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
        "list-prs",
        code=200)
    (out, err) = capfd.readouterr()
    lines = list(x.strip() for x in out.splitlines()[-2:])
    assert lines[0] == "new push requests"
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
    assert len(out.splitlines()) == 1


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
        "--index", "+pr-20180717",
        pkg.strpath)
    devpi(
        "submit-pr",
        "20180717",
        "-m", "Please accept these updated packages",
        code=200)
    devpi(
        "list-prs",
        code=200)
