# Fix the off-by-one in `total()`

`total(n)` in `total.py` should return `0 + 1 + ... + n`.

Currently `total(10)` returns `45` instead of `55`. Fix the range so both
ends are included. Do not change the function signature.
