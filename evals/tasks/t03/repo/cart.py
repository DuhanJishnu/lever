def line_total(price, qty):
    return price * qty


def cart_total(lines):
    return sum(price * qty for price, qty in lines)


def discounted(total):
    return total * 0.9 if total > 100 else total
