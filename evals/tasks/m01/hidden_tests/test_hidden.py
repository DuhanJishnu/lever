import util
from a import run
from b import run2


def test_shared_helper():
    assert util.helper(5) == 10
    assert run(5) == 11
    assert run2(5) == 9


def test_single_definition():
    import a
    import b
    assert a.helper is util.helper
    assert b.helper is util.helper
