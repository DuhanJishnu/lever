def parse_csv(text):
    rows = []
    for line in text.splitlines():
        rows.append(line.split(","))
    return rows


def parse_tsv(text):
    rows = []
    for line in text.splitlines():
        rows.append(line.split(","))
    return rows
