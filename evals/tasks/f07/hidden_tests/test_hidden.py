from topk import top_k


def test_basic():
    assert top_k([5, 1, 4, 2, 3], 3) == [5, 4, 3]


def test_edges():
    assert top_k([1, 2], 0) == []
    assert top_k([1, 2], 9) == [2, 1]
    assert top_k([-1, -5, -3], 2) == [-1, -3]
    src = [3, 1, 2]
    top_k(src, 2)
    assert src == [3, 1, 2]
