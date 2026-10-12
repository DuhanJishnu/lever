from order import ascending


def test_already_sorted():
    assert ascending([1, 2, 3]) == [1, 2, 3]


def test_duplicates_and_empty():
    assert ascending([2, 1, 2]) == [1, 2, 2]
    assert ascending([]) == []
