from store import load


def show(path):
    return f"{len(load(path))} rows"
