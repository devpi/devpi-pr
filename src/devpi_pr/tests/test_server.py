from test_devpi_server.conftest import gentmp  # noqa
from test_devpi_server.conftest import httpget  # noqa
from test_devpi_server.conftest import makemapp  # noqa
from test_devpi_server.conftest import maketestapp  # noqa
from test_devpi_server.conftest import makexom  # noqa
from test_devpi_server.conftest import mapp  # noqa
from test_devpi_server.conftest import pypiurls  # noqa
from test_devpi_server.conftest import storage_info  # noqa
from test_devpi_server.conftest import testapp  # noqa
import pytest


(makexom, mapp, testapp)  # shut up pyflakes


@pytest.fixture
def xom(request, makexom):
    import devpi_pr.server
    xom = makexom(plugins=[
        (devpi_pr.server, None)])
    return xom


@pytest.fixture
def mergeindex(mapp):
    mapp.create_and_login_user("targetuser")
    mapp.create_index("targetindex")
    mapp.create_and_login_user("mergeuser")
    api = mapp.create_index(
        "+pr-index",
        indexconfig=dict(
            type="merge",
            bases=["targetuser/targetindex"]))
    return api


def test_new_merge_index(mergeindex, testapp, xom):
    r = testapp.get_json(mergeindex.index)
    result = r.json['result']
    assert result['type'] == 'merge'
    assert result['acl_upload'] == ['mergeuser']
    assert result['bases'] == ['targetuser/targetindex']
    assert result['messages'] == []
