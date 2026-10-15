# Lever (Phase 0 scaffold)

> Lever is a coding-agent harness that makes a cheap model perform like a stronger one.
> Full plan: `Lever_Implementation_Plan.md`.

Current status: **Phase 0 — Foundations** (provider + event store + cache).

## Quickstart

```powershell
# 1. Pin Python + install deps
uv python pin 3.12
uv sync --group dev

# 2. Configure key
Copy-Item .env.example .env
# edit .env -> GEMINI_API_KEY=... and set LEVER_MODEL

# 3. Acceptance test (say-hi through provider, logged as events, 2nd run hits cache)
uv run python scripts/say_hi.py --prompt "say hi" --db .lever_events.db
uv run python scripts/say_hi.py --prompt "say hi" --db .lever_events.db  # expect: cache hit

# 4. Tests / lint
uv run pytest -q
uv run ruff check src tests
```

## Web UI (Phase 4.3)

```powershell
# backend (REST :8000, SSE, approvals)
uv run lever serve --port 8000
# frontend (Vite :5173, proxies /api -> :8000)
cd web; npm install; npm run dev
```

Populate the eval dashboard first: `uv run python evals/analyze.py
--results evals/results/<run>.jsonl --summary-json
evals/results/<run>_summary.json --charts`.

See `docs/results.md` (later) for eval numbers.
