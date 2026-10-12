# Fix aliased rows in `make_grid()`

`make_grid(n, value)` in `grid.py` builds rows that alias the same list, so
writing one cell changes a whole column (`g[0][0] = 1` also changes
`g[1][0]`). Fix it so every row is an independent list.
