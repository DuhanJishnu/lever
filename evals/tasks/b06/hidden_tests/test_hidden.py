from auth import is_admin


def test_exact_still_works():
    assert is_admin("admin") is True


def test_rejects_others():
    assert is_admin("root") is False
    assert is_admin("") is False
    assert is_admin("administrator") is False
