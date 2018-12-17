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
    assert 'create push request' in out
    assert 'list push requests' in out
    assert 'submit push request' in out
