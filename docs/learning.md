# Lever — Learning Log (Video Build Record)

> **Purpose:** A step-by-step record of **every decision and every file/change in sequence**, written so I can turn it into a detailed "making of Lever" video.
> **Convention:** Every build step = one `Step N` entry with:
> 1. **What changed** (in detail)
> 2. **Why** (the motive/narration)
> 3. **Theory/logic behind it** (whiteboard explanation)
>
> Each `Step` = one video beat. "Theory" = whiteboard; "Why" = narration; "What" = the diff you show on screen.

---

## Phase 0: Foundations (12 Oct 2026)

### Step 0 — Decisions Before Code (Feasibility + Clarifications)

1. **What:** Read `Lever_Implementation_Plan.md` (584 lines, Phases 0–6), ran env checks (`python`, `uv`, `git`, `docker`, `node`), then asked 4 questions via questionnaire: Docker strategy / Gemini key / Python version / start point. Answers locked: **Docker Desktop will be installed (design for Docker)**, **key ready via `.env`**, **pin Python 3.12 via uv**, **start at Phase 0 foundations**.
2. **Why:** The plan assumes Docker + Python 3.12 + Gemini key. Env check proved Docker missing, system Python 3.15 (plan wants 3.12), git repo absent. Guessing wrong here wastes days (e.g. building a Docker runner with no Docker).
3. **Theory:** Feasibility-first engineering. The plan's risk register lists rate limits, B0 calibration, Gemini tool-calling quirks, held-out discipline. Verifying the riskiest assumption first (API + sandbox availability) is the highest-leverage move — this is also *why* Phase 0 exists before any agent loop.

### Step 1 — `pyproject.toml` (Project Manifest, Created; Then 2 Edits)

1. **What:** Created with `name=lever`, `requires-python>=3.12,<3.13`, runtime deps (`fastapi`, `pydantic>=2`, `sse-starlette`, `google-genai`, `typer`, `python-dotenv`, `tenacity`), dev group (`pytest`, `pytest-asyncio`, `ruff`, `mypy`), `hatchling` build with `packages=["src/lever"]`, plus `[tool.ruff]`, `[tool.mypy strict]`, `[tool.pytest.ini_options]`. Edit A: added `pytest-asyncio`. Edit B: added `[tool.ruff.lint] ignore=["BLE001","S110","S112"]`.
2. **Why:** One manifest pins the whole stack so evals are reproducible; `uv sync` recreates the env exactly. `pytest-asyncio` was needed because provider tests are `async`. The ruff ignores silence blind-exception warnings on *intentional* fallback paths (cache/token-count must never crash the harness).
3. **Theory:** `src/` layout + hatchling = installed package (`import lever`) instead of fragile `sys.path` hacks. `requires-python<3.13` guards against 3.15 incompatibilities (e.g. `tree-sitter`, `pydantic` wheels lag new releases). Strict mypy from day one keeps the event/config schemas honest — schema drift is how eval numbers become lies.

### Step 2 — `.env.example` (Created)

1. **What:** Two lines: `GEMINI_API_KEY=` and `LEVER_MODEL=gemini-2.5-flash`, with header comment "copy to .env, never commit .env".
2. **Why:** Phase 0's top pitfall is leaking the API key into git. A template teaches the correct flow without containing a real secret.
3. **Theory:** Secrets-in-env is 12-factor-app practice: code reads `os.getenv`, secrets live outside version control. Default model `gemini-2.5-flash` is the cheap Flash-tier the whole thesis ("weak model + strong harness") depends on.

### Step 3 — `.gitignore` (Created; Then 1 Edit)

1. **What:** Initially ignored `.env`, `.venv/`, caches, `evals/results/`, `*.db`. Edit fixed it to ignore exactly our artifacts: `.lever_cache.jsonl`, `.lever_events.db*` (the `*.db` glob was too broad and the cache file got committed once — caught and fixed with `git rm --cached`).
2. **Why:** `.env` (secret), `.venv/` + `uv.lock` keeps env reproducible but local, `*.db`/cache files are runtime artifacts that would pollute diffs and could leak prompts.
3. **Theory:** Gitignore is a safety policy in code: what never enters history can't leak. The over-broad `*.db` lesson is worth a video beat — ignore rules must match the exact files your tools create.

### Step 4 — `README.md` (Created)

1. **What:** Title, status line ("Phase 0 — Foundations"), 4-step quickstart (pin → sync → copy `.env` → run `scripts/say_hi.py` twice), test/lint commands.
2. **Why:** The plan's Definition of Done starts with "README shows results first". Writing the quickstart now forces the acceptance path to be one copy-paste block.
3. **Theory:** README-driven development: if a newcomer can't run the acceptance in 30 seconds, the harness is too complex. This README will grow the results table/chart.

### Step 5 — `.github/workflows/ci.yml` (Created)

1. **What:** GitHub Action on push/PR: checkout → `setup-uv` → pin 3.12 → `uv sync --group dev` → `ruff check` → `pytest -q`.
2. **Why:** Catches lint/test breaks before they contaminate eval numbers. Written in Phase 0 so every later phase is guarded for free.
3. **Theory:** CI is the cheapest reviewer: deterministic, runs the exact acceptance (lint+test) on every commit. Ubuntu runner also proves we're not accidentally Windows-only (paths, shell) — important since evals run in Linux Docker.

### Step 6 — Package `__init__.py` Files (Created, Empty)

1. **What:** Five empty files marking packages: `src/lever/__init__.py`, `core/__init__.py`, `providers/__init__.py`, `store/__init__.py`, `tests/__init__.py`.
2. **Why:** Without them, `src/` layout imports (`from lever.core...`) fail on some tooling; explicit packages remove ambiguity.
3. **Theory:** Python packages 101: a directory with `__init__.py` is importable as a namespace. Empty is fine — presence is the signal.

### Step 7 — `src/lever/core/events.py` (Created)

1. **What:** `EventType` literal (12 types: `user_message`, `model_request`, `model_response`, `tool_call`, `tool_result`, `approval_request`, `approval_decision`, `context_compacted`, `policy_block`, `checkpoint`, `error`, `session_end`), `Event` Pydantic model (`id|None`, `session_id`, `seq`, `ts=time.time()`, `type`, `data: dict`), plus `new_session_id()` (12-hex-char uuid).
2. **Why:** This is design decision #1 from the plan: **event sourcing** — every model call, tool call, approval is an immutable event. Resume/fork/replay/evals all derive from this one table.
3. **Theory:** Event sourcing (Fowler): store facts (events), derive state by replay. `seq` is per-session ordering (assigned by the store, not the caller — see Step 14), `ts` defaults to now, `data` is free-form JSON so new phases add event types without migrations. Pydantic v2 validates at the boundary: corrupt events fail loudly, not silently.

### Step 8 — `src/lever/core/config.py` (Created; Then 1 Edit Removing a `type: ignore`)

1. **What:** `HarnessConfig` Pydantic model: `model`, `temperature=0.2`, `thinking_budget=None`, `max_steps=40`, `context_budget_tokens=60000`, 8 feature toggles (`tolerant_edit`, `output_truncation`, `repo_map`, `observation_masking`, `compaction`, `verify_loop`, `planner_prompt`, `loop_guard`), `best_of_n=1`, `prompt_version="v1"`, plus `b0()` classmethod returning all-toggles-off. Edit: dropped an unneeded `type: ignore` on `model_copy(update=...)` (mypy strict flagged it unused).
2. **Why:** Design decision #2: **everything is a toggle** — the ablation ladder B0..B8 becomes just running configs, not branches. `b0()` is the baseline every claim compares to.
3. **Theory:** Config-as-code for science: fixing `temperature`/`thinking_budget` across configs isolates the harness as the only variable (fair comparison). Pydantic defaults document the experimental constants (60k context budget, 40 steps) in one reviewable place.

### Step 9 — `src/lever/providers/base.py` (Created)

1. **What:** `ToolCall` model (`name`, `args`, `call_id?`), `ModelResponse` model (`text`, `tool_calls`, `input_tokens`, `output_tokens`, `raw`), and `Provider` **Protocol** with `async generate(messages, tools, config)` + `count_tokens(messages)`. `config` typed as `Any` with a comment to avoid a circular import.
2. **Why:** The plan needs Gemini now but fair ablations + free CI need swappable models. A Protocol (not base class) lets `GeminiProvider`, `FakeProvider`, and any future provider interoperate without inheritance.
3. **Theory:** Dependency inversion: `loop.py` (Phase 1) will depend on the *interface*, not Gemini. `Any`-typed config breaks the `core↔providers` import cycle while keeping runtime duck-typing. Token counts on the response feed cost/CI analysis later.

### Step 10 — `src/lever/providers/fake.py` (Created)

1. **What:** `FakeProvider`: takes a scripted `list[ModelResponse]`, returns them in order, records every call in `.calls`, `count_tokens` ≈ `chars//4`, helpers `say_hi()` and `tool_call_provider(calls, final_text)`.
2. **Why:** Deterministic, free, offline tests + the `--fake` acceptance path when no key exists. CI must never spend API money.
3. **Theory:** Test doubles 101: a scripted fake decouples harness logic (event logging, loop control) from model intelligence. `chars//4` is the standard rough token estimate (real counting comes from the API in `GeminiProvider.count_tokens`).

### Step 11 — `src/lever/providers/gemini.py` (Created; Then 3 Strictness Edits)

1. **What:** `GeminiProvider(model?, api_key?)` reading `LEVER_MODEL`/`GEMINI_API_KEY`, lazy `from google import genai` import, `count_tokens` via API with char-fallback, `async generate` with **tenacity retry (5 tries, exp backoff 2→30s)**, sync SDK call offloaded via `asyncio.to_thread`, and conversion helpers `_to_contents` (system→user `[system]` prefix, assistant→model rename, tool→user `[tool result]` framing), `_to_tools` passthrough, `_from_response` (walk `candidates[].content.parts[]` collecting `text` + `function_call{name,args}`, fallback to `.text`, usage tokens). Later edits: `str(self.model)` cast, `assert isinstance` dict-narrowing instead of `type: ignore[index]`, dropped unused ignore on the import.
2. **Why:** Retires Phase 0's riskiest unknown: **multi-turn function calling** — how tool results must be replayed in history. All quirks are quarantined in this one file so the loop never handles SDK shapes. Retry/backoff handles rate limits now, not during an overnight eval.
3. **Theory:** Adapter pattern: our canonical `{role, content}` history ↔ SDK `contents`. Key subtleties for video: (a) Gemini roles are `user`/`model` (no `system`/`assistant`/`tool`), so we fold them; (b) tool results *must* follow their calls or the API rejects history — hence explicit framing; (c) `to_thread` keeps the asyncio loop responsive for SSE streaming later; (d) exponential backoff (2,4,8…30s) is the standard answer to 429s without hammering quotas.

### Step 12 — `src/lever/providers/cache.py` (Created)

1. **What:** `cache_key(model, messages, tools, config)` = SHA-256 of canonical JSON (pydantic `model_dump`, `sort_keys=True`, `default=str`); `ResponseCache` (JSONL file, in-memory dict, loads existing lines skipping corrupt ones, `get` counts hits/misses, `put` appends one JSON line).
2. **Why:** Plan mandates this in Phase 0: it "saves money for the whole project" — re-runs, CI, and the 30-task×3-seed eval matrix would otherwise re-bill identical calls.
3. **Theory:** Content-addressed caching: identical (model, messages, tools, config) ⇒ identical key ⇒ free replay. JSONL (one JSON object per line) is append-only and crash-safe — no rewrite, no corruption window. `sort_keys` + `default=str` make the hash stable regardless of dict order or exotic types.

### Step 13 — `src/lever/store/schema.sql` (Created)

1. **What:** `events` table (`id` autoincrement PK, `session_id`, `seq`, `ts`, `type`, `data` JSON text, `UNIQUE(session_id, seq)`) + index on `(session_id, seq)`.
2. **Why:** The durable half of event sourcing. The unique constraint makes replay order physically enforceable — two writers can't fork a session's history.
3. **Theory:** SQLite WAL mode (set in Step 14) + append-only rows = simple, single-file, crash-safe event log. Index makes `read(session)` O(log n). Storing `data` as JSON text keeps the schema migration-free as event payloads evolve through Phases 1–4.

### Step 14 — `src/lever/store/sqlite.py` (Created; Then 3 Strictness Edits)

1. **What:** `EventStore(path)`: opens SQLite, `PRAGMA journal_mode=WAL`, runs schema; `append(event)` queries `MAX(seq)` per session, assigns `seq+1`, inserts, sets `event.id=lastrowid`, commits; `read(session_id)` returns ordered `Event`s; `close()`. Edits: `int(cur.lastrowid or 0)` (None-safety), `cast(EventType, typ)` instead of ignore, `cast` import added.
2. **Why:** Callers never assign `seq` — the store owns ordering, so concurrent appends can't collide and replay is canonical. This is what makes "replay reproduces the same sequence" (acceptance) literally true.
3. **Theory:** Server-assigned sequence numbers (like a log offset in Kafka): the log, not the writer, is the source of truth for order. WAL mode lets readers (UI replay, eval dashboard) read while the loop writes — needed for live SSE streaming in Phase 4.

### Step 15 — `scripts/say_hi.py` (Created)

1. **What:** Phase 0 acceptance script (`--prompt/--db/--cache/--fake/--session`): builds `HarnessConfig`, computes cache key, appends `user_message`; on hit → reuse, on miss → append `model_request`, call provider (`Fake` if no key/`--fake`, else Gemini), `cache.put`; always appends `model_response`; prints `CACHE HIT/MISS`, model text, event count, hit/miss stats.
2. **Why:** Proves the whole vertical slice: provider → cache → event log → replay, in one runnable command. Second run hitting cache is the money-saving proof.
3. **Theory:** Vertical-slice testing: before building layers (loop, tools, evals), prove the foundations compose end-to-end. Note the event asymmetry worth narrating: miss emits 3 events (user/request/response), hit emits 2 (user/response) — the log honestly records that no API call happened.

### Step 16 — Unit Tests (Created)

1. **What:** `test_store`: append×2 → seqs `[0,1]`, types ordered, replay equality. `test_cache_config`: put→get→new-instance persistence, `b0()` all toggles off. `test_providers`: fake ordering + token estimate; Gemini `_to_contents` conversion without key/network (via `__new__` bypass).
2. **Why:** Each guards one Phase 0 promise: ordering, money-saving persistence, baseline definition, and the tool-calling quirk zone — all runnable offline in CI.
3. **Theory:** Test the seams, not the vendor: we don't test Gemini's intelligence, we test *our* invariants (order, caching, conversion). `__new__` bypass is a neat trick — exercise pure conversion logic without constructing (which demands a key).

### Step 17 — Toolchain Runs + Fixes + First Commit (Executed)

1. **What:** `uv python pin 3.12` → `uv sync --group dev` (50 pkgs) → `pytest -q` 5 passed → `ruff` flagged 8 (fixed via lint-ignore config, not noqa spam) → `mypy strict` flagged 6 (fixed with real narrowing: `or 0`, `cast`, `assert isinstance`, dropping dead ignores) → `say_hi --fake` twice (MISS then HIT) → `git init`, fixed `.gitignore` after `.lever_cache.jsonl` was committed once (`git rm --cached` + recommit). Final: ruff clean, mypy clean, 5 tests green.
2. **Why:** "Do not start a phase until the previous acceptance test passes" — this run *is* the gate. Fixing lints/type errors now (not during evals) keeps later diffs clean.
3. **Theory:** Green-gate discipline: tests prove behavior, ruff proves hygiene, mypy strict proves the schemas CI and evals will trust. The accidental cache commit is a good video anecdote — artifacts that look harmless (`*.jsonl`) still get committed unless ignore rules match exactly.

**Phase 0 Exit State:** Commits `c57f5b1` → `3ae365b`. Awaiting: (a) live-key run of `say_hi.py` without `--fake` to confirm real multi-turn tool calling; (b) Docker Desktop install to unblock Phase 2's sandbox design.

---

## Phase 1: Baseline B0 (12 Oct 2026)

### Step 18 — Learned from `harness_engineering_distilled.md`, Updated the Plan

1. **What:** Read the full distilled doc (880 lines, from the mini-ai-harness reference: eval harness vs agent harness, guardrails-vs-verify, DI tools, hooks, trace-everything). Most of it confirmed our plan (Provider protocol = their model-agnostic string swap, event log = their trace, policy layer = their guardrails). Five ideas were genuinely new, so updated `Lever_Implementation_Plan.md`: (a) Phase 1 tools must be built via a `create_tools(session)` factory bound to the session — no global environment imports; (b) agent loop spec now records per-iteration context size + `stopped_by` (`model`/`guardrail`/`max_steps`) with try/finally session lifecycle and fresh context per task; (c) B6 verify loop gained trace-based semantic checks + tool hooks (verify the trace, not the model's prose); (d) B8 loop guard rewritten as composable `guard(state)` functions run before each model call; (e) Phase 2 tasks gained optional `trap` fields in `meta.json` + `fell_for_trap`/trap-rate metrics, and secondary metrics gained stopped-by breakdown. Source credited in teaching guide; doc stays at repo root.
2. **Why:** The distilled doc's core thesis — "whenever an agent makes a mistake, engineer the environment so it won't make it again" — is exactly Lever's ablation ladder, but it named mechanisms our plan left vague (who owns the environment lifecycle? how do tools get the workspace? what stops the loop besides `max_steps`?). Adopting its concrete patterns now prevents refactors later: DI tools make parallel eval runs possible, `stopped_by` makes failure analysis (Phase 5) diagnosable, trap metrics prove steering.
3. **Theory:** Five patterns for video: (i) **Dependency injection for tools** — binding tools to a session instance (vs global imports) enables testing, concurrency, cleanup; (ii) **Guardrails (structural) vs verify (semantic)** — max-iterations/context/budget can't be bypassed, while post-loop checks catch hallucinations like unverified "tests pass" claims; (iii) **Hooks** — tools emit success signals, harness subscribes, separating execution from the definition of success; (iv) **Trace everything** — per-iteration tool events + context size is the debugging interface and the raw material for eval analysis; (v) **Trap cases** — designing tasks where the obvious answer is wrong (with `fell_for_trap` tracking) measures whether the harness steers reasoning, the same way the reference's Sydney-vs-Canberra case exposes confident hallucinations.

### Step 19a — `src/lever/providers/gemini.py` Edit: Real `_to_tools` Translation

1. **What:** Replaced the passthrough `_to_tools` with a translator: our canonical defs (`{name, description, parameters}`) → `[types.Tool(function_declarations=[...])]`. Verified field names against the installed SDK (`FunctionDeclaration`: `name`, `description`, `parameters`; `Tool`: `function_declarations`).
2. **Why:** The SDK rejects OpenAI-style function schemas; without this, the first live tool-calling run would 400. Canonical defs keep us provider-agnostic (same defs render as OpenAI functions later).
3. **Theory:** Adapter pattern again — every vendor shape lives in this file. Checking `model_fields` on the installed package (not docs from memory) is the reliable move; SDK field names drift between versions.

### Step 19b — `src/lever/tools/base.py`: Cap, Path Safety, Tool/Registry

1. **What:** `MAX_OUTPUT_CHARS=20000` + `cap_output()`; `resolve_safe()` (resolve + `is_relative_to` check, rejects `..` escapes with a model-readable message); `Tool` dataclass (name/description/parameters-JSON-schema/`execute` coroutine, `.definition` property); `ToolRegistry` (`by_name`, `.definitions`, `run()` returning model-friendly errors, unknown-tool lists available names).
2. **Why:** Two B0 promises in one file: runs can't explode from giant outputs, and the model can't read/write outside the workspace. `run()` never raises — every failure becomes text the weak model can recover from (plan decision #4, early).
3. **Theory:** Agent-computer interface (SWE-agent): the tool surface *is* the model's world. Small, well-described tools with clear errors beat powerful-but-cryptic ones. `resolve()` before comparing defeats `a/../../evil` tricks that string checks miss.

### Step 19c — `src/lever/tools/fs.py`, `edit.py`, `grep.py`, `bash.py`: The 5 Tools

1. **What:** Factories `make_*_tool(root)` binding each tool to the workspace: `read_file` (missing file → "use grep" hint), `write_file` (mkdir parents), `edit_file` (**exact-match-only**: 0 hits → "copy exactly incl. whitespace", >1 → "add context", 1 → apply + unified diff), `grep` (regex, skips `.git/.venv`/binary/>1MB, max 50 matches `file:line`), `bash` (workspace cwd, timeout default 30s, `exit=` + merged output, blocking call offloaded via `asyncio.to_thread`).
2. **Why:** Deliberately naive baseline — every cleverness (fuzzy edit, ranged reads, truncation, allowlists) is a later ablation with its own measured delta. If B0 were smart, the ladder couldn't attribute gains.
3. **Theory:** Tools as capabilities: high-level (`grep`, not "read bytes"), structured returns (diff, `file:line`), verification-ready (exit codes). `to_thread` matters: a blocking `subprocess.run` inside a coroutine would freeze the whole asyncio loop (later: live SSE streaming) — ruff's ASYNC221 rule caught this.

### Step 19d — `src/lever/tools/registry.py`: `create_tools(session)` Factory

1. **What:** `create_tools(workspace)` builds all 5 tools bound to that workspace; `loop.py` imports it lazily (function-level import) to avoid a core↔tools cycle.
2. **Why:** Directly implements Step 18's DI pattern: tools bound per session, no globals → parallel eval runs + temp-dir unit tests work.
3. **Theory:** Dependency injection: the harness owns the environment, tools borrow it. Lazy import keeps the dependency arrow one-way (tools→core), a classic cycle-breaker.

### Step 19e — `src/lever/core/guards.py`: Composable Guardrails (Skeletal)

1. **What:** `GuardResult` (continue/stop+reason), `LoopState` (iterations/max_steps/context_messages/est_tokens), `Guard` callable type, `max_steps_guard`, `compose_guards` (first stop wins). B0 composes exactly one guard.
2. **Why:** Step 18's B8 design, installed as the interface now so B8 only *adds* guard functions instead of rewiring the loop.
3. **Theory:** Guardrails-vs-verify: these run *before* each model call and the model cannot bypass them (structural). Composability = each rule is independently testable.

### Step 19f — `src/lever/core/session.py`: Copy-Workspace Lifecycle

1. **What:** `Session(source)`: `open()` copies source → `.lever_workspaces/<id>/` (ignoring `.git/.venv/caches`), `git init` + baseline commit (best-effort); `close()` persists workspace (intentional in B0); `get_diff()` returns `git diff --stat`.
2. **Why:** Plan said "git worktree per session" — on Windows, copy+init gives the same clean-diffs property with zero worktree quirks. Interface (`workspace`, `open/close`, `get_diff`) is what later phases code against, so Docker/worktrees can swap in.
3. **Theory:** Harness owns the lifecycle (distilled doc's non-negotiable pattern). Baseline commit = checkpoint primitive for free (fork/replay build on this).

### Step 19g — `src/lever/core/loop.py`: The Naive Loop with Trace + Stopped_By

1. **What:** `fresh_context()` (system+user, per-task isolation), `estimate_tokens()` (chars//4, local — no API cost per iteration), `ToolEvent`/`LoopIteration` (index/outcome/tool_events/context_size)/`LoopResult` (answer/iterations/trace/stopped_by/session_id), `run_loop()`: user_message → per-step guard check → model_request → cached-or-live generate → model_response → tool_call/tool_result per call → session_end; `for/else` sets `max_steps` when never breaking; try/finally always closes the session. Assistant history notes which calls were made (`[calls: ...]`) — flagged B0 simplification for the live-model test to validate.
2. **Why:** The baseline everything compares to. Events make replay exact; trace makes failure analysis possible (Phase 5); `stopped_by` distinguishes gave-up vs guardrail-stopped; cache wiring means re-runs are free.
3. **Theory:** `for/else` (else = no break = exhausted steps) is the precise idiom for "ran out of budget". Emitting `model_request` *before* the call keeps the log honest about attempts vs completions. Local token estimates avoid N extra billed API calls per run — exact counts only where needed (B5 compaction).

### Step 19h — `src/lever/cli.py`: `lever run` + `lever sessions`

1. **What:** Typer app, `lever` console script: `run --repo --task [--config b0|file] [--db] [--cache-path] [--fake] [--model] [--max-steps]` (yaml/json overrides merged onto `b0()`); `--fake` or missing key → FakeProvider; prints session events as JSONL on stdout, summary (`stopped_by`, iterations, answer, diff stat) on stderr. Added `sessions` list command — needed because Typer flattens single-command apps (without it, `lever run` errored: "unexpected extra argument").
2. **Why:** Headless runs for evals start here; stdout-JSONL is the future event-stream protocol (Phase 6 adapter). stderr summary keeps stdout machine-parseable.
3. **Theory:** stdout = data, stderr = chatter — the Unix contract that makes `lever run ... | runner.py` composable. (Video anecdote: the framework "helpfully" collapsing one command, fixed by adding a genuinely useful second command.)

### Step 19i — Unit Tests: 9 New Tests

1. **What:** Tools: escape rejection, write→read→edit round-trip, miss/ambiguous edit errors, grep hits/misses/bad-regex, bash exit/timeout/empty, unknown tool, output cap via monkeypatched limit. Loop: direct-answer event sequence (`user_message→model_request→model_response→session_end`), max-steps guard with a never-stopping provider, and the **acceptance e2e**: toy repo with `return a - b` bug (proven failing), scripted read→edit→pytest→summary run fixes it, workspace tests go green, trace outcomes + context sizes + replay equality asserted.
2. **Why:** "Do not start Phase 2 until the acceptance passes" — the e2e test *is* the gate, in CI, offline, deterministic. Scripted provider proves plumbing; the live model proves intelligence (left for Jishnu's keyed run).
3. **Theory:** Test seams not vendors: ordering, safety, error text, trace shape. Proving the test fails *before* the fix (not just passes after) is what makes it an eval rather than a demo — this exact discipline scales into Phase 2's 30 tasks.

**Phase 1 Exit State:** B0 solves the toy bug end-to-end (scripted), replay exact, `lever run` streams JSONL. Next: Phase 2 eval harness. Still awaiting: (a) live-keyed `lever run` on a real bug (validates Gemini multi-turn history); (b) Docker Desktop install.

---

## Phase 2: Eval Harness (12 Oct 2026)

### Step 20a — `evals/runner.py`: Resumable, Parallel, Two-Backend Runner

1. **What:** `list_tasks()` (validates meta id/category + required files), `prepare_workspace()` (repo only), `stage_hidden()` (hidden tests copied at grade time + auto `conftest.py` fixing `sys.path`), `grade_local` / `grade_docker` (mount a copy, `--network none`, `lever-eval` image), `run_one()` (agent run → stage hidden → grade → full metrics dict: pass, tokens in/out, steps, wall time, tool-error/edit-failure/compaction counts, context sizes, `stopped_by`, `fell_for_trap`, diff stat, session id, `cost_usd: null`), driver with `--tasks/--config/--seeds/--backend/--jobs/--out/--dry-run/--redo`, resumable skip of finished (task, config, seed).
2. **Why:** The measuring stick everything else stands on. Grade-time staging honors "hidden tests NEVER shown to the agent" even on the local backend; resumability + semaphore make overnight 90-run matrices survivable; `cost` stays null without official rates (tokens are truth, prices are guesses).
3. **Theory:** Evals 101: fixed dataset + hidden grading + JSONL results. Counting error classes from the event log (not prose) is what makes edit-failure and stuck-run rates honest secondary metrics. `--dry-run` with FakeProvider proves plumbing while advertising pass=0 — a smoke test, never a result.

### Step 20b — `evals/analyze.py`: pass@1, Bootstrap CIs, Paired Diffs, Charts

1. **What:** Per-task rates across seeds → config mean; stdlib-only bootstrap (2000 resamples) 95% CIs; paired per-task deltas vs previous config with CIs; trap rate + stopped-by breakdown in the table; matplotlib bar-with-CI and task×config heatmap PNGs; `--summary-json` for the README pipeline.
2. **Why:** With n=15 held-out tasks, sub-~10pt deltas are noise — CIs force that honesty, and paired diffs (same tasks) are the only fair config-vs-config claim.
3. **Theory:** Bootstrap = resample tasks with replacement, recompute the mean 2000×, take the 2.5/97.5 percentiles. No normality assumption, no scipy needed. Heatmaps reveal *which* tasks move (a config can win on average while breaking specific categories — the ladder needs that detail).

### Step 20c — 30 Tasks + `SPLIT.md` + `solution.patch` per Task

1. **What:** 10 bugfix / 8 feature / 5 refactor / 4 multi-file / 3 write-tests, each with repo + issue-style `task.md` + hidden tests + `meta.json` (+ `trap` on 8: buggy-pattern remnants like `sum(range(n))`, `old_name`). Refactor tasks carry structural asserts (`hasattr`, `is_dataclass`, no `.append`) so they FAIL pre-patch — behavior-only checks would pass on the smelly code and be worthless. Write-tests tasks grade via hidden `grade.py` (file exists + ≥N tests + all pass). Split: dev b01-05/f01-04/r01-03/m01-02/t01, held-out the rest, decided before any tuning.
2. **Why:** "Mostly Python, small repos, own mutations" = fast, cheap, uncontaminated. Structural asserts are the key insight: a refactor task must test the *refactor*, not just behavior. Traps measure steering (did the fix actually land?).
3. **Theory:** Trap cases: the obvious answer is often wrong; `fell_for_trap` distinguishes "model can't" from "harness didn't steer". Held-out discipline: tuning against the final set inflates the headline number — the split is written down *before* the first real run so nobody can quietly move the line.

### Step 20d — `evals/validate_tasks.py` + the Patch Autopsy (Video Gold)

1. **What:** Per task: stage → grade (must FAIL) → `git apply solution.patch` (must apply) → grade 3× (must PASS every time — flakiness check). First full run: **20/30**. Root causes, in order: (1) hand-written unified-diff hunk headers with wrong line counts — `git apply` exited 0 yet **silently truncated files** (missing `return` → `None` returns, `IndentationError`, dropped tests); (2) generator v1 passed `a`/`b` as difflib labels (git: "inconsistent old filename"); (3) generator v2 used `lineterm=""`, collapsing the body so header-slicing deleted everything; (4) generator v3 wrote CRLF on Windows (Python text-mode `\n`→`\r\n`), git read `\r` as trailing whitespace/content mismatch. Fix: `newline="\n"` + correct labels + default lineterm. Reran: **30/30**. Repair script kept at `scripts/regen_patches.py`.
2. **Why:** "Every task must FAIL then PASS with a reference solution" is the credibility of the whole eval — a task that passes pre-patch can't measure anything, and a broken reference blocks CI. Keeping the repair script preserves the evidence trail.
3. **Theory:** Three lessons: (a) never hand-write diffs — generate them (difflib is correct by construction, humans miscount); (b) exit-code 0 ≠ correct — only the fail→pass behavior check caught the truncation, which is why validation tests behavior and not application; (c) Windows text-mode translation is a real correctness hazard for patch files — `newline="\n"` is the fix, and it belongs in every file-writing script that produces byte-sensitive artifacts.

### Step 20e — `evals/Dockerfile`, `configs.json`, `README.md`, CI Test

1. **What:** `Dockerfile` (python:3.12-slim + pytest = `lever-eval` image; no network at grade time); `configs.json` (the B0 baseline as data — the ladder B1..B8 will append configs here); `evals/README.md` (the 4 commands: validate → dry-run → real run → analyze); `tests/test_tasks_valid.py` (inventory: 30 tasks, exact category counts, SPLIT coverage, ≥6 traps + full reference gate). Ruff now excludes `evals/tasks` (task repos *intentionally* contain bugs — linting them would "fix" the eval; B006 flagged b02's mutable default — the bug IS the task). Dry-run on b01/f01/t01 → table (`pass@1 0.00`, trap rate 1.0 — correct: FakeProvider changes nothing) + both PNG charts.
2. **Why:** B0-as-data makes ablations config diffs, not code forks. The trap-rate-1.0 dry-run is a negative control: the metric correctly reports "nothing fixed" when the agent does nothing — metrics that can't show failure can't show success either.
3. **Theory:** Config-as-data is the ablation ladder made concrete (Step 8's HarnessConfig theory, now on disk). Full gates: ruff clean, mypy strict clean, 16 tests green in ~65s.

**Phase 2 Exit State:** Measuring stick built and validated; pipeline proven end-to-end with $0 spent. NOT yet done (needs keyed runs): the real B0 30×3 matrix, difficulty calibration (is B0 at 20–40%?), `docker build -t lever-eval` once Docker Desktop lands. Next: Phase 3 ladder (B1 tolerant edit first).

---

## Live debugging interlude (12 Oct 2026) — Step 21

> Jishnu ran B0 live against `bug-repo/` (single-file `add.py`, `return a - b`
> bug) with `LEVER_MODEL=gemini-3.8-flash`. The agent failed twice without
> touching the bug. This step records the investigation (4 real defects), the
> fixes, and the final verified run. Also adopts Jishnu's env-model refactor
> (model from `LEVER_MODEL`, removed from `HarnessConfig`) with tests kept green.

### Step 21a — Verdict on the two failed runs: transport bugs, not model stupidity

1. **What:** Run 1: `bash("git status; ls -la")` → cmd.exe has no `;` chaining,
   so git got a garbage command → recovered with `git status` → then the model
   emitted literal text `"[calls: bash(...)]"` with zero tool calls and stopped.
   Run 2: same parrot-stop after one good call. `bug-repo/add.py` (3-line bug)
   was never read. Model moved 2.5→3.8-flash by Jishnu (kept: `.env.example`
   updated to `gemini-3.8-flash`).
2. **Why:** Two independent defects: (a) our bash description never said the
   shell is cmd.exe; (b) the model parroted our history annotation — the
   `[calls: ...]` / `[tool result ...]:` prose framing was imitated as output
   instead of continued as action. Prose history is a B0 simplification that
   failed its live test.
3. **Theory:** A model imitates the *form* of its context. Fake call-notation in
   prose teaches a fake call-notation response; only native `FunctionCall` /
   `FunctionResponse` parts carry the "this is an action, continue it" semantics.
   Harness-engineering loop in miniature: observe failure → change the
   environment (history format), not the prompt.

### Step 21b — Fix 1: native function parts in history (`gemini.py`, `loop.py`)

1. **What:** Loop stores structured `tool_calls` on the assistant message — the
   `[calls: ...]` text hack is gone. `_to_contents` renders them via
   `Part.from_function_call` / `Part.from_function_response`; verified
   constructible against the installed SDK. `bash` description now documents
   cmd.exe (`&&`/`||`, `dir`, no `;`/`ls`). Tests: conversion test rewritten
   (native parts, no-prose assertion), new structured-history loop test.
2. **Why:** Removes both observed failure modes at the mechanism level; the
   cmd.exe hint is decision #4 (model-friendly environment description).
3. **Theory:** Adapter pattern a third time: canonical `{role, content,
   tool_calls}` history ↔ SDK parts, all quirk code in `_to_contents`. Canonical
   form stays provider-agnostic (OpenAI messages map to the same shape).

### Step 21c — Fix 2: thought signatures, bytes vs str (`base.py`, `gemini.py`)

1. **What:** First replay attempt 400'd: `Function call is missing a
   thought_signature`. Investigation: signatures arrive as **bytes** (224),
   but `ToolCall.thought_signature` was typed `str | None` → pydantic
   `ValidationError` on EVERY real call, swallowed by `except: pass` → the
   model "never called tools" for a whole debugging stretch. Fix: capture →
   base64 (JSON-safe for events/cache) → decode to bytes on replay; helpers
   `_encode_signature` / `_decode_signature`. `Part.thought_signature`
   confirmed `Optional[bytes]` against the SDK.
2. **Why:** Gemini 3.x mandates echoing the signature on function-call replay;
   without it no multi-turn run survives turn 2. Base64 keeps the event log and
   response cache JSON-serializable.
3. **Theory:** Two lessons: (a) check wire types empirically (`type()` on the
   live part), never assume str; (b) bare `except: pass` around parsing converts
   a loud validation error into a silent "model is dumb" misdiagnosis. (Kept the
   broad except — the harness must not crash on weird responses — but the guide
   records the cost.)

### Step 21d — Fix 3: the thought-divert bug (the cruelest one)

1. **What:** After adding thought-block replay, ALL calls vanished again. Root
   cause: the parser filed any part *with a signature* as a thought block and
   `continue`d — including `functionCall` parts, whose signatures then never
   became `ToolCall`s. Proved with a wire spy (response HAS the call, parse
   yields nothing) after exonerating temperature, prompt length, workspace,
   system handling (12/12 sweep: absent/folded/native all fine), call order,
   and rate limits via A/B probes. Fix: `function_call` parts always become
   `ToolCall`s (signature rides the call); only signature blocks with NO call
   and NO text become standalone thought blocks. Regression test
   `test_from_response_keeps_signed_calls` fabricates the exact shape. Docs
   (`thinking#signatures`) confirmed: resend thought blocks exactly.
2. **Why:** The load-bearing bug — nearly every real call carries a signature,
   so nearly every call was dropped. The A/B probes are the method story: when
   request bytes diff as *identical* yet outcomes differ, suspect your own
   parser — capture wire bytes, then trace parsing stepwise.
3. **Theory:** Order parser branches by specificity (call first, then thought,
   then text) — a broad thought-catch-all above the call branch eats the calls.
   Also adopted (proven harmless, kept minimal): native `system_instruction`,
   `MAX_EMPTY_RETRIES=3` + `stopped_by="empty"` for transient model-side
   empties (below).

### Step 21e — Server-side flakiness advisory (3.8-flash, today)

1. **What:** Throughout the session, tools-attached calls flapped between
   working and empty-`STOP` stretches (bare-text calls always fine; 8/8 rapid
   bursts fine in good windows; `thinking_level` LOW tested — works, but so
   does default once the window passes, so LOW is NOT the fix and was not
   adopted). Ruled out as causes: temperature, prompt length, workspace, system
   handling, call order, rate degradation. Harness posture: empty turns retried
   3× within budget, then honest `stopped_by="empty"`.
2. **Why:** B0 matrices must report `empty`-stop rates alongside pass rates, or
   model-side flakiness will read as harness failure. Retrying empties (constant
   across B0..B8) keeps the baseline measurable without biasing comparisons.
3. **Theory:** Distinguish transport bugs (deterministic, A/B-provable) from
   capacity flakiness (time-varying, identical-request flips). Never "fix" the
   harness for the latter beyond graceful handling — and never mistake the
   former for model stupidity. `thinking_budget` stays unset (default medium).

### Step 21f — Verified live run (session `aa27b6b7ea96`)

1. **What:** `lever run --repo bug-repo`: 4 iterations, `stopped_by=model`:
   `read_file(add.py)` → saw `a - b` → `edit_file` exact match applied
   (unified diff in result) → `bash(python add.py)` exit 0 ("sum of 10 and 5
   is: 15") → correct summary. Workspace diff confirms the one-line fix. Full
   suite after all changes: **22 green** (incl. 30-task reference gate).
   Committed with Jishnu's env-model refactor (model from `LEVER_MODEL`;
   `provider.model` in events/cache; new env-model test).
2. **Why:** The Phase-1 acceptance with a REAL model, not a scripted one — the
   milestone the interlude served. B0 did not write a regression-test file
   (naive baseline, no B6 verify loop — honest B0 scope).
3. **Theory:** The eval story has its first live data point: transport proven,
   baseline behavior observed (reads → edits → runs → summarizes). Everything
   from here (B1..B8 deltas) is measured against runs shaped exactly like this.

---

## Summary: File Creation Order (For Video Editing)

| Step | File(s) | Phase |
|------|---------|-------|
| 0 | (env check, questionnaire) | 0 |
| 1 | `pyproject.toml` | 0 |
| 2 | `.env.example` | 0 |
| 3 | `.gitignore` | 0 |
| 4 | `README.md` | 0 |
| 5 | `.github/workflows/ci.yml` | 0 |
| 6 | 5× `__init__.py` | 0 |
| 7 | `src/lever/core/events.py` | 0 |
| 8 | `src/lever/core/config.py` | 0 |
| 9 | `src/lever/providers/base.py` | 0 |
| 10 | `src/lever/providers/fake.py` | 0 |
| 11 | `src/lever/providers/gemini.py` | 0 |
| 12 | `src/lever/providers/cache.py` | 0 |
| 13 | `src/lever/store/schema.sql` | 0 |
| 14 | `src/lever/store/sqlite.py` | 0 |
| 15 | `scripts/say_hi.py` | 0 |
| 16 | `tests/test_store.py`, `test_cache_config.py`, `test_providers.py` | 0 |
| 17 | (toolchain run, fixes, commit) | 0 |
| 18 | (read distilled doc, updated plan) | 1 |
| 19a | `src/lever/providers/gemini.py` (edit) | 1 |
| 19b | `src/lever/tools/base.py` | 1 |
| 19c | `src/lever/tools/fs.py`, `edit.py`, `grep.py`, `bash.py` | 1 |
| 19d | `src/lever/tools/registry.py` | 1 |
| 19e | `src/lever/core/guards.py` | 1 |
| 19f | `src/lever/core/session.py` | 1 |
| 19g | `src/lever/core/loop.py` | 1 |
| 19h | `src/lever/cli.py` | 1 |
| 19i | `tests/test_tools.py`, `test_loop.py` | 1 |
| 20a | `evals/runner.py`, `evals/configs.json` | 2 |
| 20b | `evals/analyze.py` | 2 |
| 20c | 30× `evals/tasks/<id>/{repo,task.md,hidden_tests,meta.json,solution.patch}`, `evals/SPLIT.md` | 2 |
| 20d | `evals/validate_tasks.py`, `scripts/regen_patches.py`, `tests/test_tasks_valid.py` | 2 |
| 20e | `evals/Dockerfile`, `evals/README.md` | 2 |
| 21a–f | `providers/gemini.py` (native parts, signatures, thought replay), `core/loop.py` (structured calls, empty retry), `tools/bash.py` (cmd hint), `bug-repo/` fixture | live |
| 22 | `tools/edit.py` (cascade), `tools/registry.py`, `core/loop.py`, `evals/configs.json` (b1) | 3 |
| 23–24 | `evals/runner.py` (guards), `evals/analyze.py`, `docs/ablations.md`, `providers/local.py`, `docs/local_model.md` | 2–3 |
| 25 | `providers/local.py` (fences, docs, no-`tools`), server flags | local |
| 26 | `tools/base.py` (head/tail), `tools/fs.py` (ranged read), `tools/registry.py` (flag), `evals/configs.json` (b2) | 3 |
| 27 | `context/repomap.py` (new pkg), `core/loop.py` (pin + refresh), `evals/configs.json` (b3), `tests/test_repomap.py` | 3 |
| 28 | `tools/grep.py` (resolve fix), `providers/local.py` (quote shapes), `tests/test_tools.py` + `test_providers.py` | 3–local |
| 29 | `core/guards.py` (tracker+factories), `core/loop.py` (wire), `core/events.py` (nudge event), `core/config.py` + providers + runner (seed), `tests/test_guards.py` | 8 |

---

## Cost incident + local-model pivot (12 Oct 2026) — Step 24

### Step 24a — Results preserved: 78/90, resumable by construction

1. **What:** Verified `evals/results/ladder_b0b1.jsonl` = exactly 78 rows
   (13 tasks × 2 configs × 3 seeds); missing 12 = all of r03 + t01 (file is
   truth — the crash log's stray r03 lines never hit disk). The runner skips
   finished `(task, config, seed)` keys, so the 12 will fill in later with zero
   re-spend; summary + `docs/ablations.md` committed as the durable record.
2. **Why:** Your instruction: never pay for these twice. Resumability was built
   for overnight crashes; it doubles as spend protection.
3. **Theory:** Idempotent matrices (same key → skip) make eval spend
   incremental and auditable — each row is a receipt.

### Step 24b — `providers/local.py`: llama-server endpoint ($0 dev runs)

1. **What:** New `LocalProvider` speaking OpenAI-compatible `/chat/completions`
   via httpx: canonical defs → `function` tools, canonical history → OpenAI
   messages with synthetic `call_N` ids paired positionally (valid: the loop
   strictly alternates calls→results), malformed args → `_raw` instead of a
   crash, unreachable server → error pointing at `docs/local_model.md`.
   Wired as `--provider local` in CLI + runner (runner skips the cost confirm
   for local). `count_tokens` = chars//4 (documented estimate). Tested offline
   with `httpx.MockTransport` (round-trip, id pairing, down-server error).
   New `docs/local_model.md` (install → GGUF → serve → env → smoke test +
   caveats) and plan non-goal updated (Gemini stays the claims model).
2. **Why:** Nothing on this machine serves models yet (no Ollama, no
   llama-server, no GGUF found) — so the harness side is built and tested
   first; you install the ~2.5 GB model + server when ready. Day-to-day
   debugging then costs $0; Gemini returns only for final numbers.
3. **Theory:** Same Provider protocol, third transport: the loop never learns
   which model it drives. Ladders stay single-provider (a 4B local and a Flash
   model in one table would compare models, not harnesses — the exact
   confounding the fixed-temperature rule exists to prevent).

---

## Phase 3: B0-vs-B1 matrix + cost incident (12 Oct 2026) — Step 23

### Step 23a — Matrix result: ceiling effect (78/90 runs, FREE analysis)

1. **What:** Ran `analyze.py` on the partial JSONL (78 rows; 12 missing after
   the cap): B0 = B1 = **100% pass** (13 tasks, CI [1.00, 1.00]), paired delta
   **+0.00**, edit failures **0 in both**, steps ~10 tied. Fixed two Windows
   encoding crashes in the table printer (non-ASCII `↳`/`Δ` → ASCII).
2. **Why:** The dev set can't discriminate B1 — exact match sufficed on every
   task, so the cascade never engaged. Tasks written for a weaker model are too
   easy for 3.8-flash. Decision logged in `docs/ablations.md`: **KEEP on
   mechanism, UNMEASURED on outcome** (unit-tested, strictly wider, no harm).
3. **Theory:** A metric that can't show failure can't show success (same lesson
   as the trap-1.0 dry-run, inverted): 100% baselines carry zero information
   about deltas. Either harden tasks or measure secondaries — chosen: propose
   edit-stress tasks where B0 verifiably fails first.

### Step 23b — Cost guardrails (`evals/runner.py`, no API spent)

1. **What:** Runner now defaults to `--dry-run` ($0); live runs REQUIRE `--live`
   plus a printed estimate (`planned × --est-tokens-per-run`, default 25k from
   measured data) and `[y/N]` confirm (or `--yes`). Verified: unflagged run
   forces dry-run. Also: per-run try/except → error rows (a dead run can never
   kill a matrix again), `analyze.py` excludes error rows and reports
   `n_errors`.
2. **Why:** A 90-run matrix at ~21–26k tokens/run (thinking billed) tripped the
   monthly cap mid-run. The spend rate (~2M tokens for one ladder rung) was
   never estimated or approved first — process failure, fixed in code.
3. **Theory:** Cost is a first-class eval parameter: estimate before, confirm
   before, pilot (1 task × 1 seed) before matrix. Open lever for approval:
   `thinking_level` LOW for matrices (verified working; far fewer thought
   tokens) — changes model behavior, so it needs an explicit yes and must then
   stay constant across B0..B8.

---

## Phase 3: Ablation ladder (12 Oct 2026) — Step 22: B1 tolerant edit

> Rule: one feature at a time, dev-set delta before keep/discard. B0-vs-B1
> matrix (15 dev × 2 configs × 3 seeds = 90 runs) launched in background on
> commit; results → `docs/ablations.md` + Step 23.

### Step 22 — B1: tolerant `edit_file` cascade (`tools/edit.py`, `registry.py`, `loop.py`)

1. **What:** Rewrote `edit.py` as a cascade behind `tolerant_edit` (B0 path
   byte-identical, asserted by `test_b0_stays_exact`): (1) exact unique (or all
   with new `replace_all` flag); multi-hit errors list `line N` locations and
   suggest `replace_all`; (2) whitespace/indentation-normalized windows, applied
   only if exactly one candidate (ambiguous → error asking for more context);
   (3) fuzzy sliding window (`SequenceMatcher ≥ 0.9`), applied only if exactly
   one candidate, else structured miss report (closest `lines s-e`, similarity,
   6-line snippet); (4) no-candidate error. Every successful `.py` edit is
   `compile()`-checked (never executed) — breakage reverts with the exact line
   (`REVERTED … line 1`). Wiring: `create_tools(workspace, config)` reads the
   flag; `loop.py` passes its config; `evals/configs.json` gains `b1`
   (b0 + `tolerant_edit: true`). 7 new unit tests (ws-match, fuzzy typo,
   ambiguity, replace-all, syntax revert, closest-report, B0-exactness).
2. **Why:** B0's exact-match dies on the model's two most common edit failures:
   copied-with-wrong-whitespace and near-miss blocks. The cascade recovers both
   while the uniqueness rule contains over-matching (ambiguous → error, never a
   wrong edit). `compile()`-revert turns syntax breakage into a retryable
   message instead of a broken workspace the model must debug.
3. **Theory:** Matching specificity ladder (exact → normalized → fuzzy), each
   rung strictly weaker, each gated on uniqueness — precision first, recall
   second. Syntax-check-as-postcondition is the guardrails-vs-verify split at
   tool scale: the tool enforces "never break syntax" structurally so the loop
   never spends turns repairing self-inflicted damage. `replace_all` is the
   honest answer to multi-match (explicit intent) vs guessing (wrong intent).

---

## Key Architectural Decisions Captured (For Video Narration)

| # | Decision | Where It Lives | Why It Matters for Video |
|---|----------|----------------|-------------------------|
| 1 | Event sourcing (immutable log) | `core/events.py`, `store/sqlite.py` | Enables resume/fork/replay/evals from one mechanism |
| 2 | Config toggles = ablation ladder | `core/config.py` | B0..B8 are just config objects, not branches |
| 3 | Provider protocol (not base class) | `providers/base.py` | Swappable models, free CI via `FakeProvider` |
| 4 | Response cache (content-addressed) | `providers/cache.py` | Saves money on re-runs, CI, eval matrix |
| 5 | Tools bound per session (DI) | `tools/registry.py`, `tools/base.py` | Parallel evals, temp-dir tests, clean lifecycle |
| 6 | Path safety via `resolve()` | `tools/base.py:resolve_safe` | Defeats `..` escapes that string checks miss |
| 7 | Model-friendly errors (never raise) | `tools/base.py:ToolRegistry.run` | Weak models recover from good errors, die on stack traces |
| 8 | Composable guardrails | `core/guards.py` | Structural checks model can't bypass; B8 adds more |
| 9 | Fresh context per task | `core/loop.py:fresh_context` | Isolation prevents context contamination |
| 10 | Trace everything (per-iter context size) | `core/loop.py:LoopIteration` | Debugging + eval analysis raw material |
| 11 | `stopped_by` classification | `core/loop.py:LoopResult` | Diagnoses gave-up vs guardrail-stopped vs max_steps |
| 12 | Copy workspace + git baseline | `core/session.py` | Clean diffs on Windows without worktree quirks |
| 13 | Stdout=JSONL, stderr=summary | `cli.py` | Unix contract for composable pipelines |
| 14 | Hidden tests staged at grade time | `evals/runner.py:stage_hidden` | Agent never sees grading material, even locally |
| 15 | Bootstrap CIs + paired diffs | `evals/analyze.py` | Sub-10pt deltas on 15 tasks are noise; paired diffs are the only fair claim |
| 16 | Trap patterns measure steering | `meta.json:trap`, runner `_trap_check` | Distinguishes "model can't" from "harness didn't steer" |
| 17 | Refactor tasks need structural asserts | `evals/tasks/r*/hidden_tests` | Behavior-only checks pass on smelly code — worthless as evals |
| 18 | Never hand-write diffs; generate them | `scripts/regen_patches.py` | `git apply` rc=0 with wrong hunk counts silently truncates files |
| 19 | `newline="\n"` for byte-sensitive output | `scripts/regen_patches.py` | Windows text mode turns `\n` into `\r\n`, corrupting patches |
| 20 | Lint excludes task repos | `pyproject.toml:extend-exclude` | The bugs ARE the tasks — the linter must not "fix" the eval |
| 21 | Native function parts + signature echo | `providers/gemini.py`, `core/loop.py` | Prose history gets parroted; 3.x 400s without byte signatures |
| 22 | Parser specificity order (call→thought→text) | `providers/gemini.py:_from_response` | A broad catch-all above the call branch eats the calls |
| 23 | Empty-turn retry + `stopped_by="empty"` | `core/loop.py` | Model-side flakes must read as flakes, not as harness failure |
| 24 | Local provider behind the same Protocol | `providers/local.py`, `docs/local_model.md` | $0 dev loops; ladders stay single-provider or they compare models |
| 25 | Fence protocol + --no-jinja | `providers/local.py`, server flags | Small models get a text tool channel; flaky server features get disabled |
| 26 | B2 truncation + ranged reads | `tools/base.py`, `tools/fs.py`, `tools/registry.py` | Bounded context per call; second keep-on-mechanism rung |
| 27 | B3 repo map (ast + PageRank) | `context/repomap.py`, `core/loop.py` (pin + refresh) | Structure-first orientation; pure function, cheap rebuilds |
| 28 | Grep path fix + fence quotes | `tools/grep.py`, `providers/local.py` | Red traces find unit-test-blind bugs; cover observed shapes |
| 29 | B8 loop guard (guards + tracker) | `core/guards.py`, `core/loop.py`, seed plumbing | Stop thrash early; seeds must be real replicates |
| 30 | Fence multi-line + regex escaping | `providers/local.py` | Parse whole block first; test backslash inputs |

---

## Local-model bring-up (13 Oct 2026) — Step 25

### Step 25a — Server: b11565 CUDA + Gemma 3 4B Q4 on RTX 4070

1. **What:** Downloaded llama.cpp b11565 win-cuda-12.4 + cudart runtime +
   `gemma-3-4b-it-Q4_K_M.gguf` (2.37 GB) to `D:\tools`, `D:\models` (first
   attempt stalled silently at 1.4 GB — restarted with Range-resume).
   Server: `--n-gpu-layers 99` (3.3 GB VRAM confirmed via `nvidia-smi`),
   `-c 8192`, **`--no-jinja`**. Health `ok`; first `$0` chat reply `ready`.
2. **Why:** Local $0 dev loop per your directive (Gemini only for final
   numbers). Full offload because the 4070 fits it easily; 8k context covers
   B0-size histories.
3. **Theory:** Own the whole stack for dev (weights, server, harness) so
   debugging never spends budget and never depends on API weather.

### Step 25b — `--no-jinja`: the 400 class, diagnosed from the server log

1. **What:** Pilot runs 400'd (`invalid_request_error`) while identical-shape
   probes 200'd — flipping across minutes. Server log blamed Gemma-template
   tool-parser generation ("Conversation roles must alternate...") on requests
   WITH and WITHOUT `tools` keys. Bisected system/folded/absent × tools/no-tools
   (all 200 in good windows) → trigger is server-internal state, not our bytes.
   Restarted with `--no-jinja` (no Jinja execution → no parser to generate):
   zero 400s since, across ~20 requests. Provider no longer sends `tools`
   arrays at all.
2. **Why:** Chasing request bytes further was sunk cost — the log named the
   component. `--no-jinja` removes the entire failure class instead of dodging
   its unknown trigger.
3. **Theory:** When identical bytes flip outcomes across time, stop diffing
   requests and read the server's log. And: kill duplicate servers (two
   instances briefly coexisted after the restart — always verify one PID).

### Step 25c — Fence protocol: meeting the 4B model where it is

1. **What:** Gemma ignores native schemas, emitting ` ```tool_code NAME(...) ``` `
   in three observed shapes: parenthesized, `k="v"`/`k: "v"` kwargs, bare
   `NAME arg`. `_parse_fences` accepts exactly these (unknown names/args never
   become calls; colon-keys must be known schema properties so `C:\a.py` stays
   a path, not a key). Tools travel as a prose reference (`_tool_doc`) since
   native arrays are unsendable. 9 offline tests (mock transport).
2. **Why:** A dev model that can't call tools exercises nothing. Text-channel
   tools + strict fence parsing turn 0-step stops into real multi-step runs —
   the failures (wrong content, thrash) then teach the harness, which is the
   entire point of local dev.
3. **Theory:** Same principle as tolerant edits: accept the model's natural
   output shape, validate strictly, never hallucinate intent. Provider-side
   adaptation (constant across B0..B8) preserves ladder fairness.

### Step 25d — First local signal: B1 wins b01, thrashes b02 ($0)

1. **What:** b01/b02 × b0/b1 pilot: b01-b1 PASS (kwarg fence → exact edit →
   done in 2 steps); b02-b1 loops 40 steps (colon-kwarg blob misparsed as one
   arg → repeated "no such file", fixed by colon support; still fails — weak
   model, wrong content). B1's first measured win anywhere, plus the honest
   caveat (win came via parseable kwargs on the exact rung, not the cascade).
   Thrash without a loop guard is now the documented case FOR building B8.
2. **Why:** Local ladder's job is mechanism evidence and failure taxonomy, not
   pass rates. Both delivered for $0.
3. **Theory:** Tolerance multiplies attempts; without a repetition guard it can
   multiply failure too (b02: 32 edit failures in one run). Features interact —
   the ladder measures them together for exactly this reason.

---

## Phase 3: B2 truncation + ranged reads (14 Oct 2026) — Step 26

### Step 26a — Implementation (`tools/base.py`, `fs.py`, `registry.py`)

1. **What:** `truncate_lines()` (B2): head 100 + tail 50 lines with an explicit
   `[... N lines omitted ...]` marker — unlike B0's char cap it preserves the
   ending (exit codes, summaries, failing asserts). `ToolRegistry(truncate)`
   flag switches the finishing path. `read_file` gains `start_line`/`end_line`
   (1-based, schema-advertised only when the flag is on); default = first 100
   lines + `lines s-e of total` header + `re-read with start_line=N` pointer;
   small files return whole (no wrapper); inverted ranges error. Grep already
   met the spec (50 max, file:line + context) — no change. `configs.json`
   gains `b2` = b1 + `output_truncation`. 3 new unit tests (default window,
   explicit range, head/tail marker, B0 unchanged).
2. **Why:** b02-style thrash burns context on repeated full-file reads and giant
   outputs; bounding each call's context is the cheapest token lever. Ranged
   reads also teach decomposition (read → locate → re-read) instead of dumping.
3. **Theory:** Errors cluster at head (usage) and tail (verdicts); middles are
   expendable — the 100/50 asymmetry encodes that. Defaults matter: the
   first-100 + pointer shape makes the *right* next call obvious to a weak
   model, which is interface design, not just truncation.

### Step 26b — Local pilot: no breakage, no thrash ($0)

1. **What:** b01/b02 × b0/b1/b2: b2 goes 0.00 with 4.0 steps and ~3k tok/run —
   both runs stop cleanly. Same sample shows b1 thrashing 40 steps/51k tokens
   on the task it passed yesterday: n=2 on a flappy 4B model discriminates
   nothing. Decision: **KEEP on mechanism, UNMEASURED** (row in
   `docs/ablations.md`). Real measurement awaits Gemini pilots.
2. **Why:** Record the rung honestly: mechanism proven by unit tests, outcome
   unmeasurable locally. The pilot's real value is negative control — B2
   changed the observation channel without breaking completion.
3. **Theory:** Same status as B1 for the same reason (ceiling/noise, not the
   feature). The ladder's keep-on-mechanism rows are IOUs the Gemini matrix
   redeems at the end — tracked explicitly so none is forgotten.

---

## Phase 3: B3 repo map (14 Oct 2026) — Step 27

### Step 27a — Implementation (`context/repomap.py`, `loop.py`)

1. **What:** New `context/` package. `scan_file()` parses `.py` with stdlib
   `ast` (exact defs with signatures via `ast.unparse`, referenced names,
   import edges) — no tree-sitter dependency for a Python-only eval set
   (polyglot parsing noted as future work). `build_graph()` links files that
   use symbols others define. Hand-rolled 50-iteration PageRank with
   personalization (task-mentions ×3, touched-files ×2). `build_repomap()`
   renders `file [rank]` + `kind name(sig) # Lineno` under 1500 tokens
   (~6000 chars), greedy fit. Loop pins the map into the system message and
   rebuilds it after any successful edit/write (`_mutated()`), tracking
   touched paths — refresh is cheap because the function is pure.
   `configs.json` gains `b3` (all three flags on). 6 unit tests (scan, edges,
   personalization direction, budget fit, empty ws, cache-dir skip).
2. **Why:** Multi-file tasks (m01–m04) require finding the right files; the
   map front-loads structure so the model doesn't discover it one `read_file`
   at a time. Pinned-into-system = survives everything (compaction later must
   preserve tier-0). ast-over-tree-sitter: exactness beats generality when
   every task is Python — one less native dependency to break installs.
3. **Theory:** Personalized PageRank = "important" means referenced-by-others
   AND looked-at-by-you (task/touched). Rank order is placement (Lost in the
   Middle), and the 12-defs-per-file cap keeps head files readable. Pure
   rebuild-on-mutation beats incremental graph patching at this scale.

### Step 27b — Local pilot: map present, tiny repos (results pending)

1. **What:** m01 pilot (b0–b2 finished, b3 + m02 in background): all configs
   read `a.py`/`b.py` first try — but b0–b2 also read a hallucinated `util.py`
   that doesn't exist yet, while b3 (map pinned, verified in its system
   message) read only real files in 3 steps. Two-file repos can't discriminate
   a ranking feature; the honest test needs 10+ files (noted for task
   hardening). Full table when the background matrix lands.
2. **Why:** Record mechanism evidence now (map renders, pins, refreshes;
   no hallucinated reads in the one b3 trace so far), outcome later.
3. **Theory:** Orientation features pay off with scale — evaluating a map on a
   2-file repo is like testing a search engine on one document. Say so
   plainly rather than claiming a win.

---

## Red traces find bugs + fence hardening (14 Oct 2026) — Step 28

### Step 28a — Grep `relative_to` crash (all configs, found in m02 traces)

1. **What:** Every m02 run's verification `grep` died with `'...alpha.py' is
   not in the subpath of 'evals\\work_local3\\...'` — `rglob` yields absolute
   paths while the workspace root stayed relative (the runner's shape; unit
   tests used absolute tmp paths, hiding it). One-line fix (`root.resolve()`
   in `make_grep_tool`) + regression test with a relative root. After the fix
   m02 passes on b0/b2/b3 across reruns.
2. **Why:** Broken verification made models conclude false things ("renaming
   was not fully successful", hallucinated success) — a corrupted feedback
   channel poisons every config equally. Eval traces catch what unit tests
   can't: the exact production shape.
3. **Theory:** Path bugs hide behind absolute-path tests. Always test tools
   with the same relative/absolute shapes the runner uses.

### Step 28b — Single-quote fences + m02 ledger

1. **What:** b3's m02 run stopped in 1 step: the model wrote
   `edit_file(path='alpha.py', ...)` with SINGLE quotes, unparsed. Extended
   kwarg values to `'...'` (colon keys already schema-gated, so `C:\a.py`
   still parses as a path). Rerun: **m02-b3 PASS in 7 steps**. m02 ledger to
   date — b0 1/2, b1 0/2, b2 1/2, b3 1/1: variance, not ranking; every rung's
   machinery (ambiguity→`replace_all`, quote parsing, grep verify) proven live
   at least once.
2. **Why:** Third observed fence shape; each shape the parser learns turns
   1-step stops into multi-step runs. Strictness preserved (unknown
   names/keys never become calls).
3. **Theory:** Weak-model output coverage is empirical — collect shapes from
   red traces, accept exactly those. (Also recorded: b2's m02 win came via the
   ambiguity error suggesting `replace_all`, complied on the next turn — the
   B1 message design working as specified.)

### Step 29d — Multi-line fences + the backslash-escaping postmortem

1. **What:** b8's trace showed a `write_file` fence with embedded `\n`
   escapes going unparsed (3-step stop). The fence parser split blocks into
   lines first, so multi-line calls never matched — restructured to try the
   whole block, then per-line fallback, with a regression test on the exact
   live shape. While there: found my kwarg value-regex carried DOUBLED
   backslashes (`\\\\` in file = match-two-literals), silently failing only on
   backslash-containing values — which is why all simple tests passed and only
   the live `\n` case failed. Replaced with quote-agnostic `[^"]*` classes.
2. **Why:** Fourth observed fence shape; same rule (cover exactly what's
   observed, strict otherwise). The escaping bug is the lesson: regexes with
   backslash classes must be tested WITH backslash inputs — the passing suite
   gave false confidence because no test contained one.
3. **Theory:** Test the scary characters, not just the happy path. Any parser
   touching model output needs a backslash/quote/unicode case on day one.

---

## Phase 3: B8 loop guard (14 Oct 2026) — Step 29

### Step 29a — Implementation (`core/guards.py`, `loop.py`, seed plumbing)

1. **What:** Two layers behind `loop_guard` (B0–B3 byte-identical when off,
   asserted by `test_loop_guard_off_by_default`). HARD: composable factories
   `max_context_messages(300)`, `max_tokens_guard(context_budget)`,
   `time_limit_guard(600s)` + existing `max_steps`, first-stop-wins with the
   reason recorded (`LoopResult.stop_reason`, `session_end.stop_reason`,
   runner `stop_reason` + `nudges` columns). SOFT: `RepeatTracker` — call keys
   (`tool:sorted-json-args`) over a 5-turn window; same set 3× or back-to-back
   all-failed turns trigger nudge → nudge → forced re-plan → stop, delivered
   as harness user messages + `harness_nudge` events (new event type). Failure
   markers conservative (`REVERTED`, `not found`, `timed out`… — never
   `No matches`). 11 tests (guard factories, key stability, tracker
   escalation/pairs/varied-clean, off-by-default, live stop with 2+replan+stop
   events, nudge visible in history).
2. **Why:** Two observed 40-step thrashes (223s, 368s, 51k+ tokens) with zero
   progress — tolerance without a guard multiplies failure. The failure-pair
   detector exists because b02 alternated two doomed calls, defeating
   consecutive-identical checks.
3. **Theory:** Structure (hard stops) vs coaching (nudges): the former bounds
   worst-case cost unconditionally, the latter spends a little context to
   rescue borderline runs. Trip points are constants, not configs — the ladder
   varies features, and a moving tripwire would confound every comparison.

### Step 29b — Seed-aliasing methodology bug (found live, fixed)
1. **What:** The b8 pilot's seed-1 rows finished in ~1s with identical steps —
   the response cache keyed (model, messages, tools, config) but NOT seed, so
   seeds 1–2 replayed seed 0 byte-for-byte. Every prior "3-seed" matrix
   (including the 78 Gemini rows) measured 1 seed thrice — CIs overstated.
   Fix: `cache_key(..., seed)`, `run_loop(..., seed)`, runner sets
   `HarnessConfig.seed` per replicate; seed forwarded to Gemini
   (`GenerateContentConfig.seed`, verified field) and llama-server
   (`body.seed`) for genuine sampling variation. Regression tests (key
   isolation, no cross-seed cache reuse). Old cache entries simply miss.
2. **Why:** Replicates must replicate the *experiment*, not replay one
   recording. Honest uncertainty bars are load-bearing for the headline claim.
3. **Theory:** Cache identity must equal experimental identity. Anything that
   varies the trial (seed) belongs in the key — this is the same class of bug
   as the silently-truncating patches: green gates, wrong science. The Gemini
   ladder will be re-run with real seeds; past CIs should be read as n=1.

### Step 29c — b01 × 5 real seeds (local, $0): first honest local table

b01 × {b0,b1,b2,b3,b8} × seeds 0–4, all live (timings 7–193s prove no aliasing):

| config | pass@1 | steps | tok/run | notes |
|---|---|---|---|---|
| b0 | 0.20 | 3.6 | 2138 | 1 pass; lean clean stops otherwise |
| b1 | 0.60 | 10.6 | 20892 | 3 passes + one 40-step thrash (193s); tolerance widens attempts both ways |
| b2 | 0.60 | 10.4 | 21186 | same shape as b1 (one thrash) |
| b3 | 0.00 | 3.0 | 1873 | all 5 stop in 3 steps — map seems to push early give-up on 4B, unproven |
| b8 | 0.00 | 3.0 | 1873 | identical trajectories to b3; guard correctly silent, still unproven live |

Trap rate falls as pass rises (b0 .4 → b1/b2 .2: solved tasks leave no trap).
B8 verdict stands: mechanism proven scripted, live demonstration pending — a
b8-seeds-5–9 hunt runs in background; a caught thrash-cut closes the proof.

---

## Next Phases (Not Yet Implemented — For Reference)

- **Phase 3:** Ablation ladder B1–B8 — code + local-model ($0) measurement per rung;
  Gemini matrices only at the end (spend discipline). B1+B2 built, both
  keep-on-mechanism; B8 loop guard motivated by observed thrash.
- **Phase 4:** Policy layer + Web UI (FastAPI + React, context inspector, eval dashboard)
- **Phase 5:** Credibility run (held-out tasks, SWE-bench subset, results.md)
- **Phase 6:** MCP client, event-stream adapter, upstream PR, README, video, blog, v1.0 release

---

*Generated from actual codebase state as of 12 Oct 2026. Each step above corresponds to a real commit or edit sequence.*