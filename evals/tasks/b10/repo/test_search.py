from search import find_all


def test_collects_all():
    assert find_all([1, 2, 3, 4], lambda x: x % 2 == 0) == [2, 4]
