# Fix accumulation in `Calculator.add()`

`add()` in `nested.py` overwrites the total instead of accumulating it.
The faulty block is:

    def add(self, values):
    for v in values:
    if v > 0:
    self.total = v

(`Calculator().add([1, 2, 3])` returns `3` instead of `6`.) Fix the
assignment so values accumulate. Keep the positive-only filtering.
