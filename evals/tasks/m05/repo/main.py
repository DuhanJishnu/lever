from present import show
from store import load, save


def run(path):
    rows = load(path)
    save(rows, path + ".out")
    return show(path + ".out")
