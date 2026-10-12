from calc import add


def test_negatives():
    assert add(-1, -2) == -3
    assert add(-1, 2) == 1


def test_zero():
    assert add(0, 0) == 0
