# Write tests for `cart.py`

`cart.py` has three untested functions — `line_total(price, qty)`,
`cart_total(lines)` (lines are `(price, qty)` tuples), `discounted(total)`
(10% off when the total exceeds 100) — and no test files. Write thorough
tests under `tests/` (named `test_*.py`): cover empty carts, zero
quantities, totals on both sides of the 100 boundary (100 and 101).
Grading: at least 5 tests, and every test you write must pass.
