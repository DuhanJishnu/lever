import add as add_mod
import mul as mul_mod
from user import poly


def test_split_modules():
    assert add_mod.add(2, 3) == 5
    assert mul_mod.mul(2, 3) == 6
    assert poly(3) == 15


def test_monolith_removed():
    import pathlib
    assert not (pathlib.Path(add_mod.__file__).parent / "ops.py").exists()
