# Split the `ops.py` monolith into `add.py` + `mul.py`

`ops.py` hosts two unrelated operations. Split it: `add(a, b)` moves to a
new `add.py`, `mul(a, b)` moves to a new `mul.py`, then delete `ops.py`.
Update `user.py` to import from the new modules. `poly()` behavior is
unchanged (`poly(3) == 15`).
