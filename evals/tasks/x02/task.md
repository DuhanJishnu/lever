# Fix the percentage formula in `pct()`

`pct(part, whole)` in `rate.py` is wrong. It currently does
`return part / whole + 100`, which adds 100 instead of scaling by 100
(`pct(50, 100)` gives `100.5` instead of `50.0`). Fix the arithmetic so the
result is a proper percentage. Keep the zero-guard for `whole == 0`.
