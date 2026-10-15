def invoice(lines):
    total = sum(qty * price for _, qty, price in lines)
    return {"lines": len(lines), "total": total}


def render(inv):
    return f"{inv['lines']} lines, total {inv['total']:.2f}"
