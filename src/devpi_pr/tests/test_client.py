import pytest
try:
    import devpi.main
except ImportError:
    pytestmark = pytest.mark.skip("No devpi-client installed")


def test_commands(capsys):
    with pytest.raises(SystemExit) as e:
        devpi.main.main(['devpi', '--help'])
    (out, err) = capsys.readouterr()
    assert e.value.code == 0
    assert 'abort review of push request' in out
    assert 'approve push request' in out
    assert 'cancel push request' in out
    assert 'create push request' in out
    assert 'delete push request' in out
    assert 'list push requests' in out
    assert 'reject push request' in out
    assert 'start reviewing push request' in out
    assert 'submit push request' in out


@pytest.fixture(autouse=True)
def devpi_pr_data_dir(monkeypatch, tmpdir):
    path = tmpdir.join('devpi-pr-user-data').ensure_dir()
    monkeypatch.setattr("devpi_pr.client.devpi_pr_data_dir", path.strpath)
    yield path


def test_devpi_pr_review_data_initial(devpi_pr_data_dir):
    from devpi_pr.client import devpi_pr_review_data
    path = devpi_pr_data_dir.join("reviews.json")
    assert not path.exists()
    with devpi_pr_review_data() as data:
        assert data == {}
    assert path.exists()


def test_devpi_pr_review_data_lock(devpi_pr_data_dir):
    from devpi_pr.client import devpi_pr_review_data
    lock_path = devpi_pr_data_dir.join("reviews.lock")
    path = devpi_pr_data_dir.join("reviews.json")
    assert not path.exists()
    with devpi_pr_review_data():
        assert lock_path.exists()
        assert not path.exists()
        with pytest.raises(FileExistsError):
            with devpi_pr_review_data():
                pass


def test_devpi_pr_review_data_no_change(devpi_pr_data_dir):
    from devpi_pr.client import devpi_pr_review_data
    path = devpi_pr_data_dir.join("reviews.json")
    assert not path.exists()
    with devpi_pr_review_data() as data:
        assert data == {}
    assert path.exists()
    mtime = path.stat().mtime
    with devpi_pr_review_data() as data:
        assert data == {}
    assert mtime == path.stat().mtime


def test_devpi_pr_review_data_change_persistet(devpi_pr_data_dir):
    from devpi_pr.client import devpi_pr_review_data
    path = devpi_pr_data_dir.join("reviews.json")
    assert not path.exists()
    with devpi_pr_review_data() as data:
        assert data == {}
        data['foo'] = 'bar'
    assert path.exists()
    with devpi_pr_review_data() as data:
        assert data == {'foo': 'bar'}
