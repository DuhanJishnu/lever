from billing import invoice, render


def summary(lines):
    inv = invoice(lines)
    return render(inv) + " due"
