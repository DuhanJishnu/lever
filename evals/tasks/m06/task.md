# Add shared money formatting used by two modules

Both `billing.py` (`render()`) and `report.py` (`summary()`) format money
as raw numbers. Create a new `money.py` with `fmt(cents)` returning strings
like `"$1.99"` for `199` (cents to dollars, always 2 decimals), and make
BOTH modules use it as their single source (importable as `billing.fmt`
and `report.fmt`). Behavior of `render()`/`summary()` outputs is unchanged
apart from the formatting.
