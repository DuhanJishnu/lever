from nested import Calculator


def test_add_accumulates():
    assert Calculator().add([1, 2, 3]) == 6
