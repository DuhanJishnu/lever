Example 1 — fix a one-line bug:
task: total(n) should sum 0..n but returns 45 for n=10
plan: 1. read total.py, 2. fix range, 3. run pytest
read_file total.py -> `def total(n): return sum(range(n))`
edit_file total.py, old `sum(range(n))`, new `sum(range(n + 1))` -> applied
bash pytest -q -> 3 passed
answer: fixed off-by-one; pytest 3 passed

Example 2 — rename across two files:
plan: 1. read both files, 2. rename definition, 3. update import, 4. run tests
grep old_name -> alpha.py:1, beta.py:1
edit_file alpha.py with full `def` line for uniqueness -> applied
edit_file beta.py import line -> applied
bash pytest -q -> 2 passed
answer: renamed in 2 files; pytest 2 passed
