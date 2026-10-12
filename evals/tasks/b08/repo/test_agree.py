from agree import agrees


def test_case_and_space():
    assert agrees(" Yes ") is True
