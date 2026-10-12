from avg import average


def test_normal():
    assert average([1, 2, 3]) == 2
    assert average([2.5, 2.5]) == 2.5


def test_single():
    assert average([7]) == 7
