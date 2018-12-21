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
        "bases=%s/dev" % devpi.user,
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
        "bases=%s/dev" % devpi.user,
        code=400)
    (out, err) = capfd.readouterr()
    assert "indexname 'invalid_prefix' must start with '+pr-'." in out


def test_manual_index_creation_invalid_name(capfd, devpi):
    devpi(
        "index", "-c",
        "+pr-invalid[name]",
        "type=merge",
        "bases=%s/dev" % devpi.user,
        code=400)
    (out, err) = capfd.readouterr()
    assert "indexname 'invalid[name]' contains characters" in out


def test_index_creation(capfd, devpi, getjson, makepkg):
    devpi(
        "pr",
        "20180717",
        "%s/dev" % devpi.user,
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


def test_approval(devpi, getjson, makepkg):
    devpi(
        "pr",
        "20180717",
        "%s/dev" % devpi.user,
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
    devpi(
        "approve-pr",
        "20180717",
        "-m", "The push request was accepted",
        code=200)
    data = getjson("+pr-20180717")["result"]
    assert data["states"] == ["new", "pending", "approved"]
    assert data["messages"] == [
        "New push request",
        "Please accept these updated packages",
        "The push request was accepted"]
    data = getjson("%s/dev" % devpi.user)["result"]
    assert data['projects'] == ['hello']
    data = getjson("%s/dev/hello" % devpi.user)["result"]
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
        'dst': '%s/dev' % devpi.user,
        'message': 'The push request was accepted',
        'src': '%s/+pr-20180717' % devpi.user,
        'what': 'push',
        'who': '%s' % devpi.user}


def test_pr_listing(capfd, devpi, getjson, makepkg):
    # a new one
    devpi(
        "pr",
        "20181217",
        "%s/dev" % devpi.user,
        code=200)
    # a submitted one
    devpi(
        "pr",
        "20180717",
        "%s/dev" % devpi.user,
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
