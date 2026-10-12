from slug import slugify


def test_basic():
    assert slugify("Hello World") == "hello-world"


def test_runs_and_edges():
    assert slugify("  A   B  ") == "a-b"
    assert slugify("Caf\u00e9!") == "caf"
    assert slugify("") == ""
    assert slugify("a_b") == "a-b"
