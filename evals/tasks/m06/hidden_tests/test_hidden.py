from billing import invoice, render
from money import fmt
from report import summary


def test_money_format():
    assert fmt(199) == "$1.99"
    assert fmt(5) == "$0.05"
    assert fmt(0) == "$0.00"


def test_single_source():
    import billing
    import report

    assert billing.fmt is fmt
    assert report.fmt is fmt
    assert summary([("a", 1, 199)]) == "1 lines, total $1.99 due"
