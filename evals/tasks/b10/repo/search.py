def find_all(xs, pred):
    for x in xs:
        if pred(x):
            return x
