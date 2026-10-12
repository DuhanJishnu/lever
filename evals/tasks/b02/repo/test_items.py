from items import add_item


def test_independent_calls():
    assert add_item(1) == [1]
    assert add_item(2) == [2]
