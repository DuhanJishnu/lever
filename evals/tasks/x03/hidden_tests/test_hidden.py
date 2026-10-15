from parsers import parse_csv, parse_tsv


def test_csv_untouched():
    assert parse_csv("a,b\nc,d") == [["a", "b"], ["c", "d"]]


def test_tsv_single_and_empty():
    assert parse_tsv("x\ty") == [["x", "y"]]
    assert parse_tsv("") == []
