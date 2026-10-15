# Fix the dropped record in `save()`

Exporting through `run()` in `main.py` loses the last record: 3 rows in,
2 rows out. The symptom shows in `present.py`'s count, but the cause is
elsewhere — `save()` in `store.py` iterates `rows[:-1]` instead of all rows.
(`api.py` and `config.py` are unrelated; leave them alone.) Fix the loop so
every row round-trips, including single-row files.
