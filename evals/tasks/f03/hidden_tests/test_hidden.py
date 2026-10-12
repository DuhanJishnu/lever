import pytest

from chunk import chunk


def test_even():
    assert chunk([1, 2, 3, 4], 2) == [[1, 2], [3, 4]]


def test_remainder():
    assert chunk([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]


def test_edges():
    assert chunk([], 3) == []
    assert chunk([1], 5) == [[1]]
    assert chunk([1, 2], 1) == [[1], [2]]


def test_bad_size():
    with pytest.raises(ValueError):
        chunk([1, 2], 0)
