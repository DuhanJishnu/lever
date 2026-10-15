from rates import rate_for, with_tax


def test_lowercase_and_unknown():
    assert rate_for("ca") == 0.072
    assert rate_for("XX") == 0.0


def test_with_tax():
    assert with_tax(100.0, "TX") == 106.2
    assert with_tax(100.0, "XX") == 100.0
