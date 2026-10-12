from ops import add, mul


def poly(x):
    return add(mul(x, x), mul(2, x))
