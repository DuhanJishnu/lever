from main import run
from store import load


def test_export_keeps_all_rows(tmp_path):
    src = tmp_path / "in.csv"
    src.write_text("a,1\nb,2\nc,3\n", encoding="utf-8")
    assert run(str(src)) == "3 rows"
    assert load(str(src) + ".out") == [["a", "1"], ["b", "2"], ["c", "3"]]
