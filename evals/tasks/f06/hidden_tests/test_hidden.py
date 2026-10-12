from pal import is_palindrome


def test_simple():
    assert is_palindrome("racecar") is True
    assert is_palindrome("hello") is False


def test_ignores_case_noise_and_empty():
    assert is_palindrome("A man, a plan, a canal: Panama") is True
    assert is_palindrome("No 'x' in Nixon") is True
    assert is_palindrome("") is True
    assert is_palindrome("ab") is False
