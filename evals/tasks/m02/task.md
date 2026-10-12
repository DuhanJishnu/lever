# Rename `old_name` to `new_name` across modules

The function `old_name()` in `alpha.py` (used by `caller()` there and
imported by `beta.py`) must be renamed to `new_name()`. Update the
definition and every reference in both files. Behavior is unchanged; no
stale `old_name` references may remain in either module.
