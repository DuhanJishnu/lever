from main import run
from store import load, save


def test_single_row_survives(tmp_path):
    src = tmp_path / "one.csv"
    src.write_text("only,1\n", encoding="utf-8")
    assert run(str(src)) == "1 rows"
    assert load(str(src) + ".out") == [["only", "1"]]


def test_save_roundtrip(tmp_path):
    dst = tmp_path / "r.csv"
    rows = [["a", "1"], ["b", "2"]]
    save(rows, str(dst))
    assert load(str(dst)) == rows
