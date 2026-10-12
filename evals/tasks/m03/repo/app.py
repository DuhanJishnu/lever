TIMEOUT = 30
RETRIES = 3


def get_timeout():
    return TIMEOUT


def fetch(key):
    return f"{key}:{TIMEOUT}:{RETRIES}"
