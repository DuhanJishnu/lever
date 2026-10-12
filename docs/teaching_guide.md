# Lever — Teaching Guide (video build log)

> Purpose: a step-by-step record of **every decision and every file/change in sequence**,
> written so Jishnu can turn it into a detailed "making of Lever" video.
> Convention from now on: every new build step appends a `Step N` entry below with:
> 1. **What changed** (in detail), 2. **Why**, 3. **Theory/logic behind it**.

How to use for video: each `Step` = one video beat. The "Theory" subsection is your
whiteboard explanation; the "Why" is your narration motive; "What" maps to the diff
you show on screen.

---

## Phase 0: Foundations (12 Oct 2026)

### Step 0 — Decisions before code (feasibility + clarifications)

1. **What:** Read `Lever_Implementation_Plan.md` (584 lines, Phases 0–6), ran env checks
   (`python`, `uv`, `git`, `docker`, `node`), then asked 4 questions via questionnaire:
   Docker strategy / Gemini key / Python version / start point.
   Answers locked: **Docker Desktop will be installed (design for Docker)**,
   **key ready via `.env`**, **pin Python 3.12 via uv**, **start at Phase 0 foundations**.
2. **Why:** The plan assumes Docker + Python 3.12 + Gemini key. Env check proved
   Docker missing, system Python 3.15 (plan wants 3.12), git repo absent.
   Guessing wrong here wastes days (e.g. building a Docker runner with no Docker).
3. **Theory:** Feasibility-first engineering. The plan's risk register lists rate limits,
   B0 calibration, Gemini tool-calling quirks, held-out discipline. Verifying the
   riskiest assumption first (API + sandbox availability) is the highest-leverage move —
   this is also *why* Phase 0 exists before any agent loop.

### Step 1 — `pyproject.toml` (project manifest, created; then 2 edits)

1. **What:** Created with `name=lever`, `requires-python>=3.12,<3.13`,
   runtime deps (`fastapi`, `pydantic>=2`, `sse-starlette`, `google-genai`, `typer`,
   `python-dotenv`, `tenacity`), dev group (`pytest`, `pytest-asyncio`, `ruff`, `mypy`),
   `hatchling` build with `packages=["src/lever"]`, plus `[tool.ruff]`, `[tool.mypy strict]`,
   `[tool.pytest.ini_options]`. Edit A: added `pytest-asyncio`. Edit B: added
   `[tool.ruff.lint] ignore=["BLE001","S110","S112"]`.
2. **Why:** One manifest pins the whole stack so evals are reproducible; `uv sync`
   recreates the env exactly. `pytest-asyncio` was needed because provider tests are
   `async`. The ruff ignores silence blind-exception warnings on *intentional*
   fallback paths (cache/token-count must never crash the harness).
3. **Theory:** `src/` layout + hatchling = installed package (`import lever`) instead of
   fragile `sys.path` hacks. `requires-python<3.13` guards against 3.15 incompatibilities
   (e.g. `tree-sitter`, `pydantic` wheels lag new releases). Strict mypy from day one
   keeps the event/config schemas honest — schema drift is how eval numbers become lies.

### Step 2 — `.env.example` (created)

1. **What:** Two lines: `GEMINI_API_KEY=` and `LEVER_MODEL=gemini-2.5-flash`,
   with header comment "copy to .env, never commit .env".
2. **Why:** Phase 0's top pitfall is leaking the API key into git. A template teaches
   the correct flow without containing a real secret.
3. **Theory:** Secrets-in-env is 12-factor-app practice: code reads `os.getenv`,
   secrets live outside version control. Default model `gemini-2.5-flash` is the
   cheap Flash-tier the whole thesis ("weak model + strong harness") depends on.

### Step 3 — `.gitignore` (created; then 1 edit)

1. **What:** Initially ignored `.env`, `.venv/`, caches, `evals/results/`, `*.db`.
   Edit fixed it to ignore exactly our artifacts: `.lever_cache.jsonl`,
   `.lever_events.db*` (the `*.db` glob was too broad and the cache file got committed
   once — caught and fixed with `git rm --cached`).
2. **Why:** `.env` (secret), `.venv/` + `uv.lock` keeps env reproducible but local,
   `*.db`/cache files are runtime artifacts that would pollute diffs and could leak prompts.
3. **Theory:** Gitignore is a safety policy in code: what never enters history can't leak.
   The over-broad `*.db` lesson is worth a video beat — ignore rules must match the
   exact files your tools create.

### Step 4 — `README.md` (created)

1. **What:** Title, status line ("Phase 0 — Foundations"), 4-step quickstart
   (pin → sync → copy `.env` → run `scripts/say_hi.py` twice), test/lint commands.
2. **Why:** The plan's Definition of Done starts with "README shows results first".
   Writing the quickstart now forces the acceptance path to be one copy-paste block.
3. **Theory:** README-driven development: if a newcomer can't run the acceptance in
   30 seconds, the harness is too complex. This README will grow the results table/chart.

### Step 5 — `.github/workflows/ci.yml` (created)

1. **What:** GitHub Action on push/PR: checkout → `setup-uv` → pin 3.12 →
   `uv sync --group dev` → `ruff check` → `pytest -q`.
2. **Why:** Catches lint/test breaks before they contaminate eval numbers.
   Written in Phase 0 so every later phase is guarded for free.
3. **Theory:** CI is the cheapest reviewer: deterministic, runs the exact acceptance
   (lint+test) on every commit. Ubuntu runner also proves we're not accidentally
   Windows-only (paths, shell) — important since evals run in Linux Docker.

### Step 6 — `src/lever/__init__.py`, `core/__init__.py`, `providers/__init__.py`, `store/__init__.py`, `tests/__init__.py` (created, empty)

1. **What:** Five empty files marking packages.
2. **Why:** Without them, `src/` layout imports (`from lever.core...`) fail on some
   tooling; explicit packages remove ambiguity.
3. **Theory:** Python packages 101: a directory with `__init__.py` is importable as
   a namespace. Empty is fine — presence is the signal.

### Step 7 — `src/lever/core/events.py` (created)

1. **What:** `EventType` literal (12 types: `user_message`, `model_request`,
   `model_response`, `tool_call`, `tool_result`, `approval_request`,
   `approval_decision`, `context_compacted`, `policy_block`, `checkpoint`, `error`,
   `session_end`), `Event` Pydantic model
   (`id|None`, `session_id`, `seq`, `ts=time.time()`, `type`, `data: dict`), plus
   `new_session_id()` (12-hex-char uuid).
2. **Why:** This is design decision #1 from the plan: **event sourcing** — every model
   call, tool call, approval is an immutable event. Resume/fork/replay/evals all derive
   from this one table.
3. **Theory:** Event sourcing (Fowler): store facts (events), derive state by replay.
   `seq` is per-session ordering (assigned by the store, not the caller — see Step 12),
   `ts` defaults to now, `data` is free-form JSON so new phases add event types without
   migrations. Pydantic v2 validates at the boundary: corrupt events fail loudly, not silently.

### Step 8 — `src/lever/core/config.py` (created; then 1 edit removing a `type: ignore`)

1. **What:** `HarnessConfig` Pydantic model: `model`, `temperature=0.2`,
   `thinking_budget=None`, `max_steps=40`, `context_budget_tokens=60000`,
   8 feature toggles (`tolerant_edit`, `output_truncation`, `repo_map`,
   `observation_masking`, `compaction`, `verify_loop`, `planner_prompt`, `loop_guard`),
   `best_of_n=1`, `prompt_version="v1"`, plus `b0()` classmethod returning all-toggles-off.
   Edit: dropped an unneeded `type: ignore` on `model_copy(update=...)` (mypy strict flagged it unused).
2. **Why:** Design decision #2: **everything is a toggle** — the ablation ladder B0..B8
   becomes just running configs, not branches. `b0()` is the baseline every claim compares to.
3. **Theory:** Config-as-code for science: fixing `temperature`/`thinking_budget` across
   configs isolates the harness as the only variable (fair comparison). Pydantic defaults
   document the experimental constants (60k context budget, 40 steps) in one reviewable place.

### Step 9 — `src/lever/providers/base.py` (created)

1. **What:** `ToolCall` model (`name`, `args`, `call_id?`), `ModelResponse` model
   (`text`, `tool_calls`, `input_tokens`, `output_tokens`, `raw`), and `Provider`
   **Protocol** with `async generate(messages, tools, config)` + `count_tokens(messages)`.
   `config` typed as `Any` with a comment to avoid a circular import.
2. **Why:** The plan needs Gemini now but fair ablations + free CI need swappable models.
   A Protocol (not base class) lets `GeminiProvider`, `FakeProvider`, and any future
   provider interoperate without inheritance.
3. **Theory:** Dependency inversion: `loop.py` (Phase 1) will depend on the *interface*,
   not Gemini. `Any`-typed config breaks the `core↔providers` import cycle while keeping
   runtime duck-typing. Token counts on the response feed cost/CI analysis later.

### Step 10 — `src/lever/providers/fake.py` (created)

1. **What:** `FakeProvider`: takes a scripted `list[ModelResponse]`, returns them in order,
   records every call in `.calls`, `count_tokens` ≈ `chars//4`, helpers `say_hi()` and
   `tool_call_provider(calls, final_text)`.
2. **Why:** Deterministic, free, offline tests + the `--fake` acceptance path when no key
   exists. CI must never spend API money.
3. **Theory:** Test doubles 101: a scripted fake decouples harness logic (event logging,
   loop control) from model intelligence. `chars//4` is the standard rough token estimate
   (real counting comes from the API in `GeminiProvider.count_tokens`).

### Step 11 — `src/lever/providers/gemini.py` (created; then 3 strictness edits)

1. **What:** `GeminiProvider(model?, api_key?)` reading `LEVER_MODEL`/`GEMINI_API_KEY`,
   lazy `from google import genai` import, `count_tokens` via API with char-fallback,
   `async generate` with **tenacity retry (5 tries, exp backoff 2→30s)**, sync SDK call
   offloaded via `asyncio.to_thread`, and conversion helpers `_to_contents` (system→user
   `[system]` prefix, assistant→model rename, tool→user `[tool result]` framing),
   `_to_tools` passthrough, `_from_response` (walk `candidates[].content.parts[]`
   collecting `text` + `function_call{name,args}`, fallback to `.text`, usage tokens).
   Later edits: `str(self.model)` cast, `assert isinstance` dict-narrowing instead of
   `type: ignore[index]`, dropped unused ignore on the import.
2. **Why:** Retires Phase 0's riskiest unknown: **multi-turn function calling** —
   how tool results must be replayed in history. All quirks are quarantined in this one
   file so the loop never handles SDK shapes. Retry/backoff handles rate limits now,
   not during an overnight eval.
3. **Theory:** Adapter pattern: our canonical `{role, content}` history ↔ SDK `contents`.
   Key subtleties for video: (a) Gemini roles are `user`/`model` (no `system`/`assistant`/
   `tool`), so we fold them; (b) tool results *must* follow their calls or the API rejects
   history — hence explicit framing; (c) `to_thread` keeps the asyncio loop responsive
   for SSE streaming later; (d) exponential backoff (2,4,8…30s) is the standard answer
   to 429s without hammering quotas.

### Step 12 — `src/lever/providers/cache.py` (created)

1. **What:** `cache_key(model, messages, tools, config)` = SHA-256 of canonical JSON
   (pydantic `model_dump`, `sort_keys=True`, `default=str`); `ResponseCache`
   (JSONL file, in-memory dict, loads existing lines skipping corrupt ones, `get`
   counts hits/misses, `put` appends one JSON line).
2. **Why:** Plan mandates this in Phase 0: it "saves money for the whole project" —
   re-runs, CI, and the 30-task×3-seed eval matrix would otherwise re-bill identical calls.
3. **Theory:** Content-addressed caching: identical (model, messages, tools, config) ⇒
   identical key ⇒ free replay. JSONL (one JSON object per line) is append-only and
   crash-safe — no rewrite, no corruption window. `sort_keys` + `default=str` make the
   hash stable regardless of dict order or exotic types.

### Step 13 — `src/lever/store/schema.sql` (created)

1. **What:** `events` table (`id` autoincrement PK, `session_id`, `seq`, `ts`, `type`,
   `data` JSON text, `UNIQUE(session_id, seq)`) + index on `(session_id, seq)`.
2. **Why:** The durable half of event sourcing. The unique constraint makes replay order
   physically enforceable — two writers can't fork a session's history.
3. **Theory:** SQLite WAL mode (set in Step 14) + append-only rows = simple, single-file,
   crash-safe event log. Index makes `read(session)` O(log n). Storing `data` as JSON text
   keeps the schema migration-free as event payloads evolve through Phases 1–4.

### Step 14 — `src/lever/store/sqlite.py` (created; then 3 strictness edits)

1. **What:** `EventStore(path)`: opens SQLite, `PRAGMA journal_mode=WAL`, runs schema;
   `append(event)` queries `MAX(seq)` per session, assigns `seq+1`, inserts, sets
   `event.id=lastrowid`, commits; `read(session_id)` returns ordered `Event`s;
   `close()`. Edits: `int(cur.lastrowid or 0)` (None-safety), `cast(EventType, typ)`
   instead of ignore, `cast` import added.
2. **Why:** Callers never assign `seq` — the store owns ordering, so concurrent appends
   can't collide and replay is canonical. This is what makes "replay reproduces the same
   sequence" (acceptance) literally true.
3. **Theory:** Server-assigned sequence numbers (like a log offset in Kafka): the log,
   not the writer, is the source of truth for order. WAL mode lets readers (UI replay,
   eval dashboard) read while the loop writes — needed for live SSE streaming in Phase 4.

### Step 15 — `scripts/say_hi.py` (created)

1. **What:** Phase 0 acceptance script (`--prompt/--db/--cache/--fake/--session`):
   builds `HarnessConfig`, computes cache key, appends `user_message`; on hit → reuse,
   on miss → append `model_request`, call provider (`Fake` if no key/`--fake`, else Gemini),
   `cache.put`; always appends `model_response`; prints `CACHE HIT/MISS`, model text,
   event count, hit/miss stats.
2. **Why:** Proves the whole vertical slice: provider → cache → event log → replay,
   in one runnable command. Second run hitting cache is the money-saving proof.
3. **Theory:** Vertical-slice testing: before building layers (loop, tools, evals), prove
   the foundations compose end-to-end. Note the event asymmetry worth narrating:
   miss emits 3 events (user/request/response), hit emits 2 (user/response) — the log
   honestly records that no API call happened.

### Step 16 — `tests/test_store.py`, `tests/test_cache_config.py`, `tests/test_providers.py` (created)

1. **What:** `test_store`: append×2 → seqs `[0,1]`, types ordered, replay equality.
   `test_cache_config`: put→get→new-instance persistence, `b0()` all toggles off.
   `test_providers`: fake ordering + token estimate; Gemini `_to_contents` conversion
   without key/network (via `__new__` bypass).
2. **Why:** Each guards one Phase 0 promise: ordering, money-saving persistence,
   baseline definition, and the tool-calling quirk zone — all runnable offline in CI.
3. **Theory:** Test the seams, not the vendor: we don't test Gemini's intelligence,
   we test *our* invariants (order, caching, conversion). `__new__` bypass is a neat
   trick — exercise pure conversion logic without constructing (which demands a key).

### Step 17 — Toolchain runs + fixes + first commit (executed)

1. **What:** `uv python pin 3.12` → `uv sync --group dev` (50 pkgs) →
   `pytest -q` 5 passed → `ruff` flagged 8 (fixed via lint-ignore config, not noqa spam)
   → `mypy strict` flagged 6 (fixed with real narrowing: `or 0`, `cast`, `assert
   isinstance`, dropping dead ignores) → `say_hi --fake` twice (MISS then HIT) →
   `git init`, fixed `.gitignore` after `.lever_cache.jsonl` was committed once
   (`git rm --cached` + recommit). Final: ruff clean, mypy clean, 5 tests green.
2. **Why:** "Do not start a phase until the previous acceptance test passes" — this run
   *is* the gate. Fixing lints/type errors now (not during evals) keeps later diffs clean.
3. **Theory:** Green-gate discipline: tests prove behavior, ruff proves hygiene, mypy
   strict proves the schemas CI and evals will trust. The accidental cache commit is a
   good video anecdote — artifacts that look harmless (`*.jsonl`) still get committed
   unless ignore rules match exactly.

**Phase 0 exit state:** commits `c57f5b1` → `3ae365b`. Awaiting from Jishnu:
(a) live-key run of `say_hi.py` without `--fake` to confirm real multi-turn tool calling;
(b) Docker Desktop install to unblock Phase 2's sandbox design.

---

## Phase 1: Baseline B0 (starts next — append Step 18+ here)
