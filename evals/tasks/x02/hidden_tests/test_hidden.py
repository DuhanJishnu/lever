from rate import pct


def test_zero_whole():
    assert pct(5, 0) == 0


def test_full_and_zero_part():
    assert pct(3, 3) == 100.0
    assert pct(0, 7) == 0.0
