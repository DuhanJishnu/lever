from flat import flatten


def test_basic():
    assert flatten([[1, 2], [3], []]) == [1, 2, 3]


def test_edges():
    assert flatten([]) == []
    assert flatten([[], []]) == []
    assert flatten([[1]]) == [1]
