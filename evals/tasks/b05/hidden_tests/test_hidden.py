from count import count_words


def test_empty():
    assert count_words([]) == {}


def test_single_repeated():
    assert count_words(["x", "x", "x"]) == {"x": 3}
