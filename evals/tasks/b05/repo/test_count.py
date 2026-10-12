from count import count_words


def test_basic():
    assert count_words(["a", "b", "a"]) == {"a": 2, "b": 1}
