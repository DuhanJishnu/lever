import config


def load(path):
    with open(path, encoding="utf-8") as f:
        return [line.rstrip("\n").split(config.DELIMITER) for line in f
                if line.strip()]


def save(rows, path):
    with open(path, "w", encoding="utf-8") as f:
        for r in rows[:-1]:
            f.write(config.DELIMITER.join(r) + "\n")
