# Convert `Point` to a dataclass in `point.py`

`Point` in `point.py` hand-rolls `__init__` and `__eq__`. Replace it with a
`@dataclass` holding `x` and `y`. Equality semantics must stay identical
(same coordinates → equal, different → unequal, non-`Point` → unequal).
