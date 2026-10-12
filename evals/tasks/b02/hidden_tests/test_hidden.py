from items import add_item


def test_no_shared_default():
    a = add_item("x")
    b = add_item("y")
    assert a == ["x"] and b == ["y"] and a is not b


def test_explicit_list_untouched():
    src = [9]
    assert add_item(1, src) == [9, 1]
