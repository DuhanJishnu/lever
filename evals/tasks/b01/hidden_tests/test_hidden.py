from total import total


def test_hundred():
    assert total(100) == 5050


def test_zero():
    assert total(0) == 0
