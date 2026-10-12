from auth import is_admin


def test_padded_name():
    assert is_admin("  admin ") is True
