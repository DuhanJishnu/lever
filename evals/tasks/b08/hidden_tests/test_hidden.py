from agree import agrees


def test_exact():
    assert agrees("yes") is True


def test_rejects():
    assert agrees("no") is False
    assert agrees("y") is False
    assert agrees("YES please") is False
