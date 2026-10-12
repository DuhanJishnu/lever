from alpha import caller, new_name
from beta import shifted


def test_rename_complete():
    assert new_name(1) == 2
    assert caller(1) == 20
    assert shifted(1) == 1


def test_no_stale_references():
    import alpha
    import beta
    for mod in (alpha, beta):
        src = open(mod.__file__, encoding="utf-8").read()
        assert "old_name" not in src
