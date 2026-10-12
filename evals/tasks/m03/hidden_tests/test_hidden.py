import app
import config
import worker


def test_single_source():
    assert config.TIMEOUT == 30
    assert config.RETRIES == 3
    assert app.get_timeout() == 30
    assert app.fetch("k") == "k:30:3"
    assert worker.attempts() == 4


def test_shared_values():
    assert app.TIMEOUT == worker.TIMEOUT == config.TIMEOUT
