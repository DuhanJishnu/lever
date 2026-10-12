# Split `process()` into two functions in `users.py`

`process(users)` in `users.py` does two jobs: filtering active users and
formatting names. Split it into `active_users(users)` (returns the active
user dicts, in order) and `format_names(users)` (returns stripped, titled
names for every user given). Keep `process(users)` working by delegating to
the two new functions. Empty input gives `[]` everywhere.
