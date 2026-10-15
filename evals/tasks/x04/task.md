# Fix case-insensitive lookup in `rate_for()`

`rate_for(code)` in `rates.py` fails for uppercase codes: `rate_for("TX")`
returns `0.0` instead of `0.062`, because the table keys are lowercase and
the lookup does not normalize case. (The file is long — read it in ranges
rather than dumping it whole.) Fix the lookup; `with_tax()` should then work
for any case too. Unknown codes must still return `0.0`.
