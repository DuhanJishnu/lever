# Fix sort direction in `ascending()`

`ascending(xs)` in `order.py` promises ascending order but returns descending
order (`ascending([3, 1, 2])` gives `[3, 2, 1]`). Fix the sort direction.
