from dedup import dedup


def test_order_kept():
    assert dedup([3, 1, 3, 2, 1]) == [3, 1, 2]


def test_edges():
    assert dedup([]) == []
    assert dedup(["a", "a", "b"]) == ["a", "b"]
    src = [1, 1, 2]
    dedup(src)
    assert src == [1, 1, 2]
