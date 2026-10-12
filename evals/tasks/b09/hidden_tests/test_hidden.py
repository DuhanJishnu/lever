from grid import make_grid


def test_shape_and_value():
    g = make_grid(3, value=7)
    assert g == [[7, 7, 7], [7, 7, 7], [7, 7, 7]]
    g[2][2] = 0
    assert g[0][2] == 7 and g[1][2] == 7


def test_one():
    assert make_grid(1) == [[0]]
