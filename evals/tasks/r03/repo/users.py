def process(users):
    out = []
    for u in users:
        if u.get("active"):
            out.append(u["name"].strip().title())
    return out
