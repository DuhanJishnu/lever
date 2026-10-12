from order import ascending


def test_basic():
    assert ascending([3, 1, 2]) == [1, 2, 3]
