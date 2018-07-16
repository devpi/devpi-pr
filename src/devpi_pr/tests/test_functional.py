def test_manual_index_creation(capfd, devpi):
    devpi(
        "index", "-c",
        "+pr-manual",
        "type=merge",
        "bases=%s/dev" % devpi.user,
        code=200)
    (out, err) = capfd.readouterr()


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
