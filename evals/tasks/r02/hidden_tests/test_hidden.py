from pathlib import Path

import squares


def test_behavior():
    assert squares.even_squares([1, 2, 3, 4]) == [4, 16]
    assert squares.even_squares([]) == []
    assert squares.even_squares([1, 3]) == []


def test_uses_comprehension():
    src = Path(squares.__file__).read_text(encoding="utf-8")
    assert ".append(" not in src
