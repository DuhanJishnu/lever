import dataclasses

from point import Point


def test_is_dataclass():
    assert dataclasses.is_dataclass(Point)


def test_behavior():
    assert Point(1, 2) == Point(1, 2)
    assert Point(1, 2) != Point(1, 3)
    assert Point(1, 2) != "nope"
    p = Point(3, 4)
    assert (p.x, p.y) == (3, 4)
