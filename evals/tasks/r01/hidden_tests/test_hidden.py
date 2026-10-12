import totals


def test_behavior_preserved():
    assert totals.sum_even([1, 2, 3, 4]) == 6
    assert totals.sum_odd([1, 2, 3, 4]) == 4
    assert totals.sum_even([]) == 0


def test_helper_exists_and_works():
    assert hasattr(totals, "sum_if")
    assert totals.sum_if([1, 2, 3], lambda n: True) == 6
    assert totals.sum_if([2, 4], lambda n: n > 3) == 4
