# Fix early return in `find_all()`

`find_all(xs, pred)` in `search.py` returns only the first match (and `None`
when nothing matches) instead of the full list of matches. Collect every
matching element into a list and return it; return `[]` when nothing matches.
