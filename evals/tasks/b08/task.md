# Normalize input in `agrees()`

`agrees(answer)` in `agree.py` only accepts the exact string `"yes"`, so
`" Yes "` and `"YES"` are wrongly rejected. Normalize case and surrounding
whitespace before comparing. Partial matches like `"y"` or `"YES please"`
must stay rejected.
