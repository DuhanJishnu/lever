# Fix the `KeyError` in `count_words()`

`count_words(words)` in `count.py` crashes with `KeyError` on the first
unseen word because it increments a missing key. Fix it so unseen words
start at zero. Empty input must return `{}`.
