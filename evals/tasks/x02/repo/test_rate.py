from rate import pct


def test_half():
    assert pct(50, 100) == 50.0
