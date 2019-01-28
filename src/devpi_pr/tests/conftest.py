from __future__ import print_function
from contextlib import closing
from devpi_common.url import URL
from io import BytesIO
from time import sleep
import py
import pytest
import requests
import socket
import subprocess
import sys
import tarfile


def get_open_port(host):
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind((host, 0))
        s.listen(1)
        port = s.getsockname()[1]
    return port


def wait_for_port(host, port, timeout=60):
    while timeout > 0:
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
            s.settimeout(1)
            if s.connect_ex((host, port)) == 0:
                return timeout
        sleep(1)
        timeout -= 1
    raise RuntimeError(
        "The port %s on host %s didn't become accessible" % (port, host))


def wait_for_server_api(host, port, timeout=60):
    timeout = wait_for_port(host, port, timeout=timeout)
    while timeout > 0:
        try:
            r = requests.get("http://%s:%s/+api" % (host, port), timeout=1)
        except requests.exceptions.ConnectionError:
            pass
        else:
            if r.status_code == 200:
                return
        sleep(1)
        timeout -= 1
    raise RuntimeError(
        "The api on port %s, host %s didn't become accessible" % (port, host))


def _liveserver(serverdir):
    host = 'localhost'
    port = get_open_port(host)
    path = py.path.local.sysfind("devpi-server")
    assert path
    try:
        args = [
            str(path), "--serverdir", str(serverdir), "--debug",
            "--host", host, "--port", str(port)]
        subprocess.check_call(args + ['--init', '--no-root-pypi'])
    except subprocess.CalledProcessError as e:
        # this won't output anything on Windows
        print(
            getattr(e, 'output', "Can't get process output on Windows"),
            file=sys.stderr)
        raise
    p = subprocess.Popen(args)
    wait_for_server_api(host, port)
    return (p, URL("http://%s:%s" % (host, port)))


@pytest.yield_fixture(scope="session")
def url_of_liveserver(request):
    serverdir = request.config._tmpdirhandler.mktemp("liveserver")
    (p, url) = _liveserver(serverdir)
    try:
        yield url
    finally:
        p.terminate()
        p.wait()


@pytest.fixture
def cmd_devpi(tmpdir, monkeypatch):
    """ execute devpi subcommand in-process (with fresh init) """
    from devpi.main import initmain

    def ask_confirm(msg):
        print("%s: yes" % msg)
        return True

    clientdir = tmpdir.join("client")

    def run_devpi(*args, **kwargs):
        callargs = []
        for arg in ["devpi", "--clientdir", clientdir] + list(args):
            if isinstance(arg, URL):
                arg = arg.url
            callargs.append(str(arg))
        print("*** inline$ %s" % " ".join(callargs))
        hub, method = initmain(callargs)
        monkeypatch.setattr(hub, "ask_confirm", ask_confirm)
        expected = kwargs.get("code", None)
        try:
            method(hub, hub.args)
        except SystemExit as sysex:
            hub.sysex = sysex
            if expected is None or expected < 0 or expected >= 400:
                # we expected an error or nothing, don't raise
                pass
            else:
                raise
        finally:
            hub.close()
        if expected is not None:
            if expected == -2:  # failed-to-start
                assert hasattr(hub, "sysex")
            elif isinstance(expected, list):
                assert hub._last_http_stati == expected
            else:
                if not isinstance(expected, tuple):
                    expected = (expected, )
                if hub._last_http_status not in expected:
                    pytest.fail(
                        "got http code %r, expected %r" % (
                            hub._last_http_status, expected))
        return hub

    run_devpi.clientdir = clientdir
    return run_devpi


@pytest.fixture
def devpi_username():
    attrname = '_count'
    count = getattr(devpi_username, attrname, 0)
    setattr(devpi_username, attrname, count + 1)
    return "user%d" % count


@pytest.fixture
def target_username():
    attrname = '_count'
    count = getattr(target_username, attrname, 0)
    setattr(target_username, attrname, count + 1)
    return "target%d" % count


@pytest.fixture
def devpi(cmd_devpi, devpi_username, target_username, url_of_liveserver):
    cmd_devpi("use", url_of_liveserver.url, code=200)
    cmd_devpi("user", "-c", target_username, "password=123", "email=123")
    cmd_devpi("login", target_username, "--password", "123")
    cmd_devpi("index", "-c", "dev", "push_requests_allowed=true")
    cmd_devpi("user", "-c", devpi_username, "password=123", "email=123")
    cmd_devpi("login", devpi_username, "--password", "123")
    cmd_devpi("index", "-c", "dev", "push_requests_allowed=true")
    cmd_devpi("use", "dev")
    cmd_devpi.user = devpi_username
    cmd_devpi.target = target_username
    return cmd_devpi


@pytest.fixture
def getjson(devpi_username, url_of_liveserver):
    def getjson(userindex):
        if '/' not in userindex:
            userindex = "%s/%s" % (devpi_username, userindex)
        jsontype = "application/json"
        headers = {"Accept": jsontype, "content-type": jsontype}
        r = requests.get(
            url_of_liveserver.joinpath(userindex).url,
            headers=headers)
        if r.status_code != 200:
            raise ValueError(r.reason)
        return r.json()
    return getjson


@pytest.fixture
def makepkg(tmpdir):
    def makepkg(basename, content, name, version):
        fn = tmpdir.join(basename)
        with open(fn.strpath, "wb") as f:
            pkg_info = '\n'.join([
                "Metadata-Version: 1.1",
                "Name: %s" % name,
                "Version: %s" % version]).encode('utf-8')
            tf = tarfile.open(basename, mode='w:gz', fileobj=f)
            tinfo = tarfile.TarInfo('PKG-INFO')
            tinfo.size = len(pkg_info)
            tf.addfile(tinfo, BytesIO(pkg_info))
            tinfo = tarfile.TarInfo('content')
            tinfo.size = len(content)
            tf.addfile(tinfo, BytesIO(content))
            tf.close()
        return fn
    return makepkg