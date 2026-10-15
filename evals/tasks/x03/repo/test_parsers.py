from parsers import parse_csv, parse_tsv


def test_tsv_splits_tabs():
    assert parse_tsv("a\tb\nc\td") == [["a", "b"], ["c", "d"]]
