from mdict import merge


def test_b_wins():
    assert merge({"x": 1, "y": 2}, {"y": 3, "z": 4}) == {"x": 1, "y": 3, "z": 4}


def test_no_mutation_and_empty():
    a, b = {"x": 1}, {"x": 2}
    assert merge(a, b) == {"x": 2}
    assert (a, b) == ({"x": 1}, {"x": 2})
    assert merge({}, {}) == {}
