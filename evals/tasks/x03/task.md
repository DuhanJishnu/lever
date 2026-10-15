# Fix the delimiter in `parse_tsv()` only

`parse_tsv()` in `parsers.py` splits on commas instead of tabs, so
`parse_tsv("a\\tb")` gives `[["a\\tb"]]` instead of `[["a", "b"]]`.
Fix ONLY the TSV function — `parse_csv()` is correct and must keep
splitting on commas.
