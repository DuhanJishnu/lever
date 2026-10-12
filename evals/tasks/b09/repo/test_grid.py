from grid import make_grid


def test_rows_independent():
    g = make_grid(2)
    g[0][0] = 1
    assert g[1][0] == 0
