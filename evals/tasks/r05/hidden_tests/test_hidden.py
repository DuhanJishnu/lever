from pathlib import Path

import sumup


def test_behavior():
    assert sumup.total([1, 2, 3]) == 6
    assert sumup.total([]) == 0
    assert sumup.total([-1, 1]) == 0


def test_uses_builtin_sum():
    src = Path(sumup.__file__).read_text(encoding="utf-8")
    assert "sum(" in src
