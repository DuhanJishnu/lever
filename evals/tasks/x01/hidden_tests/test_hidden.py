from nested import Calculator


def test_empty_and_negatives():
    assert Calculator().add([]) == 0
    assert Calculator().add([-1, 5]) == 5


def test_state_accumulates_across_calls():
    c = Calculator()
    c.add([1, 2])
    assert c.add([10]) == 13
