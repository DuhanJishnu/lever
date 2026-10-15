from rates import rate_for, with_tax


def test_uppercase_lookup():
    assert rate_for("TX") == 0.062
