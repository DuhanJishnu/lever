# Move the shared helper into `util.py`

`helper()` is defined in `a.py` and imported by `b.py` via
`from a import helper`. Move `helper()` into a new module `util.py`, and make
both `a.py` and `b.py` import it from there (`from util import helper`).
Behavior of `run()` and `run2()` must be unchanged, and there must be exactly
one definition of the helper.
