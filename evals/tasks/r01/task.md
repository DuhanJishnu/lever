# Extract a shared helper in `totals.py`

`sum_even()` and `sum_odd()` in `totals.py` duplicate the same accumulate-if
loop. Extract a helper named `sum_if(nums, pred)` that sums elements
satisfying `pred`, and make both functions delegate to it. Behavior must be
identical (including empty input → `0`).
