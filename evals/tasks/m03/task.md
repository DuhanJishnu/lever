# Centralize settings in `config.py`

`app.py` and `worker.py` each hardcode their own `TIMEOUT = 30` and
`RETRIES = 3` copies, which can drift apart. Create a new `config.py` holding
both constants as the single source of truth, and make `app.py` and
`worker.py` import their values from it. All behavior and attribute access
(`app.TIMEOUT`, `worker.RETRIES`, …) must keep working.
