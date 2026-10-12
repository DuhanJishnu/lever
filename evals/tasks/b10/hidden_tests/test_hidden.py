from search import find_all


def test_none_match():
    assert find_all([1, 3], lambda x: x % 2 == 0) == []


def test_all_and_empty():
    assert find_all([2, 4], lambda x: x % 2 == 0) == [2, 4]
    assert find_all([], lambda x: True) == []
