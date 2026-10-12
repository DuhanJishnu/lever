# Fix shared state in `add_item()`

`add_item(item, lst=[])` in `items.py` leaks items between calls: the default
list is created once and reused, so `add_item(1)` then `add_item(2)` returns
`[1, 2]` instead of `[2]`.

Fix it so each call without an explicit list gets a fresh list. Keep the
signature compatible (`add_item(item)` and `add_item(item, some_list)`).
