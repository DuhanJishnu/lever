# Lever

> **Lever** is a coding-agent harness that makes a cheap model (Gemini Flash-tier) solve more coding tasks by wrapping it with context engineering, tolerant tools, verification loops, and safety policies — and *proves it with numbers*.

**Core claim:**
> "With the Lever harness, Gemini Flash solves X% of coding tasks versus Y% with a bare agent loop, using Z% fewer tokens — measured on 30 held-out tasks with bootstrap 95% CIs."
> *(Full results after held-out run in Phase 5 · Nov 2026)*

---

## Results (dev set · in progress)

> [!NOTE]
> Only Gemini numbers support headline claims. Local (Gemma 3 4B) numbers are used for $0 harness debugging only and are never mixed into Gemini tables.

### Gemini ladder — B0 vs B1 (12 Oct 2026 · 78/90 runs)

| config | tasks | pass@1 | 95% CI | tok/run | steps | edit-fail |
|--------|-------|--------|--------|---------|-------|-----------|
| B0 (bare) | 13 | **1.00** | [1.00, 1.00] | 21 424 | 10.2 | 0 |
| B1 (+tolerant edit) | 13 | **1.00** | [1.00, 1.00] | 25 888 | 10.3 | 0 |
| → paired B1-vs-B0 | | d +0.00 | [+0.00, +0.00] (n=13) | | | |

*Dev tasks are too easy for Gemini Flash — ceiling effect at 100%. B1's tolerant cascade is kept on mechanism (unit-tested, zero harm signal). Full ladder numbers pending Gemini re-run after spending guard was added.*

### Local ladder — mechanism pilots (Gemma 3 4B · $0)

| config | tasks | pass@1 | steps | key finding |
|--------|-------|--------|-------|-------------|
| B0 | b01, b02 | 0.00 | 1–3 | clean stops, no tool-use |
| B1 | b01, b02 | 0.50 | 2–40 | first live win via kwarg fence; thrash on weak model |
| B2 | b01, b02 | 0.33 | 4–8 | truncation kills thrash, tokens drop 10× |
| B6 | b01 | — | 19 | verify loop fires: model claimed done on unchanged file → caught |

Charts: `evals/results/pass_rate.png` · `evals/results/heatmap.png`

---

## What Lever does — the ablation ladder

Each feature is a boolean toggle in `HarnessConfig`. Running configs B0 → B8 in order isolates each feature's contribution.

| Config | Adds | Hypothesis |
|--------|------|------------|
| **B0** | Bare ReAct loop, 5 tools, 40-step cap | Baseline |
| **B1** | Tolerant edit (exact → whitespace → fuzzy → structured error) | Fewer failed edits |
| **B2** | Head+tail output truncation · ranged `read_file` | Less context waste |
| **B3** | Personalized-PageRank repo map (pinned in system prompt) | Finds right files faster |
| **B4** | Observation masking — keep last 6 tool outputs in full | Longer effective horizon |
| **B5** | Context compaction with pinned memory tiers | Survives long tasks |
| **B6** | Verify loop — run visible tests when model claims done | Catches false "done" |
| **B7** | Planner prompt v2 + `todo` scratchpad tool | Better decomposition |
| **B8** | Composable hard guards + soft repeat tracker (nudge → replan → stop) | Fewer stuck runs |

---

## Architecture

```
Web UI (React + Vite)       CLI (Typer)        Eval runner
        \                       |                  /
         +------- SSE / REST (FastAPI) -----------+
                               |
+-------------- Harness core --------------------------+
|  Agent loop (core/loop.py)  |  Policy engine         |
|  Context engine             |  (approve/deny/ask)    |
|  ├─ Repo map (PageRank)     |                        |
|  ├─ Observation masking     |  Session store         |
|  └─ Compaction              |  (SQLite, WAL mode)    |
|  Tool runtime               |                        |
|  ├─ read / write / edit     |  Response cache        |
|  ├─ grep / bash             |  (JSONL, SHA-256 key)  |
|  └─ todo (scratchpad)       |                        |
+-----------------------------------------------------+
         |                         |
   Gemini API / llama-server    Workspace (git copy)
```

**Key design decisions:**

| # | Decision | Why |
|---|----------|-----|
| 1 | Event sourcing — every action is an immutable SQLite row | Replay, fork, and evals come from one mechanism |
| 2 | All features are toggles in `HarnessConfig` | Ablation study = running configs B0..B8 |
| 3 | Provider protocol — swap Gemini ↔ local ↔ fake | Same agent loop, different model; fake = free CI |
| 4 | DI for tools — `create_tools(workspace, config)` per session | Parallel eval runs without race conditions |
| 5 | Tools return model-friendly errors | Weak models recover from good errors; die on tracebacks |
| 6 | Git copy per session + baseline commit | Clean `git diff` for UI; `..` escapes rejected |
| 7 | Response cache (SHA-256 of model+messages+tools+config+seed) | Repeat eval runs cost $0 |

---

## Quickstart

### Prerequisites

- Python 3.12, [uv](https://docs.astral.sh/uv/)
- A Gemini API key **or** a local llama-server (see [docs/local_model.md](docs/local_model.md) for $0 runs)

```powershell
# 1. Clone and install
git clone https://github.com/DuhanJishnu/lever
cd lever
uv python pin 3.12
uv sync --group dev

# 2. Configure credentials
Copy-Item .env.example .env
# Edit .env → set GEMINI_API_KEY and LEVER_MODEL (e.g. gemini-2.0-flash)

# 3. Smoke test (say-hi, hits cache on second run)
uv run python scripts/say_hi.py --prompt "say hi" --db .lever_events.db
uv run python scripts/say_hi.py --prompt "say hi" --db .lever_events.db  # expect: cache hit

# 4. Run the agent on a repo
uv run lever run --repo bug-repo --task "Fix the failing test in add.py"

# 5. Tests + lint
uv run pytest -q
uv run ruff check src tests
```

### Web UI

```powershell
# Backend (REST + SSE)
uv run lever serve --port 8000

# Frontend (separate terminal)
cd web
npm install
npm run dev   # → http://localhost:5173
```

The UI has three tabs:
- **Run** — start a new session, watch events live via SSE, approve policy prompts
- **Sessions** — list all past sessions, replay event history, fork from any step
- **Evals** — dashboard from `evals/results/*_summary.json`

---

## Headless CLI

```powershell
# Run against a repo (B0 config, Gemini)
uv run lever run \
  --repo ./my-repo \
  --task "Add input validation to process_order()" \
  --config b0 \
  --db .lever_events.db

# Use a local model ($0)
uv run lever run --repo ./my-repo --task "..." --provider local

# Dry-run (FakeProvider, no API key, $0 — tests plumbing only)
uv run lever run --repo ./my-repo --task "..." --fake

# List sessions
uv run lever sessions --db .lever_events.db

# Start the HTTP server
uv run lever serve --port 8000
```

Stdout = newline-delimited JSON events (machine-readable).
Stderr = human summary (`session=... stopped_by=... diff_stat=...`).

---

## Running Evals

```powershell
# Dry-run (FakeProvider — tests plumbing, no cost)
uv run python evals/runner.py --tasks b01 b02 --dry-run --out evals/results/dry.jsonl

# Local model pilot ($0, 2 tasks × 1 seed)
uv run python evals/runner.py \
  --tasks b01 b02 --seeds 1 \
  --provider local --backend local \
  --out evals/results/local_smoke.jsonl

# Real Gemini run (costs money — requires --live)
uv run python evals/runner.py \
  --tasks b01 b02 b03 --config evals/configs.json \
  --seeds 3 --live \
  --out evals/results/r1.jsonl

# Analysis: pass@1, bootstrap 95% CIs, paired diffs, charts
uv run python evals/analyze.py \
  --results evals/results/r1.jsonl \
  --summary-json evals/results/r1_summary.json \
  --charts
```

**Runner flags:**
- `--live` is required for real API calls (default = dry-run, \$0)
- `--provider local` uses llama-server (free, see [docs/local_model.md](docs/local_model.md))
- `--backend docker` grades inside `python:3.12-slim --network none` (reproducible)
- `--jobs 2` controls parallel runs (respect rate limits)
- Resumable: completed `(task, config, seed)` tuples are skipped on re-run

---

## Eval task format

```
evals/tasks/<task_id>/
  repo/              # starting code (agent sees this)
  task.md            # issue-style description
  hidden_tests/      # graded AFTER the run (agent never sees)
  meta.json          # {id, category, difficulty, test_cmd, timeout, trap?}
  solution.patch     # reference solution (validated in CI)
```

30 tasks total across 5 categories: bugfix, feature, refactor, multi-file, write-tests.
Dev/held-out split (decided before any tuning): see [evals/SPLIT.md](evals/SPLIT.md).

**Trap tasks:** `meta.json` records a `"trap"` — the plausible-but-wrong answer a weak model typically gives. The runner reports `fell_for_trap` per run; configs that reduce trap rate are genuinely steering the model.

---

## Project layout

```
lever/
  src/lever/
    core/        loop.py  config.py  events.py  session.py  guards.py  verify.py
    providers/   base.py  gemini.py  local.py   fake.py     cache.py
    tools/       base.py  fs.py      edit.py    grep.py     bash.py    todo.py    registry.py
    context/     repomap.py  masking.py  compaction.py
    policy/      engine.py  rules.py
    prompts/     registry.py  v1/  v2/
    server/      app.py  sessions.py
    cli.py
  evals/
    tasks/       <task_id>/{repo/, task.md, hidden_tests/, meta.json, solution.patch}
    runner.py    analyze.py    validate_tasks.py
    configs.json             # B0..B8 HarnessConfig definitions
    results/     *.jsonl  *_summary.json  *.png
    SPLIT.md     Dockerfile
  web/           src/{App.tsx, components/, api.ts, hooks.ts}  package.json
  tests/         test_loop.py  test_guards.py  test_tools.py  test_compaction.py ...
  scripts/       say_hi.py  regen_patches.py
  docs/          ablations.md  local_model.md  learning.md
  pyproject.toml
```

---

## Policy engine

The policy layer intercepts every tool call before execution. Four rules ship by default:

| Rule | Behaviour |
|------|-----------|
| `ConfineRule` | Deny any file-tool path that escapes the workspace (defence-in-depth on top of `resolve_safe`) |
| `BashAllowlistRule` | Allow `python`, `pytest`, `git`, `ls`, `cat`, etc.; **ask** for anything else |
| `TokenBudgetRule` | **Ask** once cumulative model tokens pass the configured budget |
| `InstallThenPushRule` | After any `pip/npm/uv install`, **ask** before `git push` or network access |

Decisions: `allow` (silent), `deny` (blocked event logged), `ask` (SSE `approval_request` event; UI shows a modal; agent waits up to 10 min for human decision).

---

## Local model ($0 dev runs)

For day-to-day harness debugging, run Gemma 3 4B via llama.cpp. Reserve Gemini for final numbers. Provider tables are **never mixed**.

```powershell
# Start llama-server (Windows, CUDA)
llama-server.exe -m C:\models\gemma-3-4b-q4km.gguf `
  --port 8080 -c 8192 --n-gpu-layers 99 --no-jinja

# Point Lever at it
$env:LEVER_LOCAL_URL = "http://localhost:8080/v1"
$env:LEVER_LOCAL_MODEL = "gemma-3-4b"

uv run lever run --repo bug-repo --task "Fix add.py" --provider local --max-steps 5
```

Full setup: [docs/local_model.md](docs/local_model.md).

---

## Tech stack

| Layer | Choice |
|-------|--------|
| Language | Python 3.12 · `uv` · `asyncio` |
| Agent loop | Custom ReAct loop (`core/loop.py`) |
| Model access | `google-genai` SDK (Gemini) · `httpx` (OpenAI-compatible local) |
| Server | FastAPI · `sse-starlette` (SSE) · Pydantic v2 |
| Storage | SQLite WAL — append-only events table |
| Code intelligence | `ast` (stdlib) — definitions, references, PageRank |
| Frontend | React 19 · Vite · TypeScript · Tailwind CSS v4 |
| Eval stats | Bootstrap CIs · paired per-task diffs · `matplotlib` charts |
| Quality | `ruff` · `mypy` · `pytest` · GitHub Actions |

---

## CI

GitHub Actions runs on every push and PR:

```yaml
uv run ruff check src tests   # lint
uv run pytest -q              # 200+ tests (FakeProvider — free, deterministic)
```

Tests cover: agent loop, guards + repeat tracker, tolerant edit cascade, compaction tiers, repo map + PageRank, observation masking, verify loop, policy rules, provider conversion, eval runner plumbing.

---

## What didn't work / honest notes

- **B1 on Gemini dev set**: unmeasured — dev tasks are too easy (Gemini Flash copies `old_str` exactly, cascade never fires). Real signal needs edit-stress tasks.
- **B3 on local model**: repo map caused early give-up at n=2-file tasks. Likely model fixation on the map over actual file reading. Measurement deferred to Gemini.
- **B7 scratchpad (`todo` tool)**: Gemma 3 4B never calls it despite following the v2 workflow prose shape. Prompt adherence is partial; tool use unproven without Gemini pilots.
- **Spending cap incident (12 Oct 2026)**: 90-run Gemini matrix tripped the monthly cap (~₹150). Runner now defaults to `--dry-run`; `--live` + token estimate + `[y/N]` confirm required for real runs.

See [docs/ablations.md](docs/ablations.md) for the full per-feature decision log.

---

## Roadmap

- [ ] Held-out eval run (Phase 5 · Nov 2026) — headline numbers
- [ ] Docker sandbox for bash isolation (`--network none`)
- [ ] Full context inspector in the web UI (stacked bar: pinned / working-set / observations vs budget)
- [ ] SWE-bench Lite subset (40–50 tasks) — stretch goal
- [ ] MCP client (`tools/mcp.py`) — expose one MCP server's tools to the agent
- [ ] Upstream PR (Omnigent adapter spec or similar)

---

## License

MIT · © 2026 Jishnu Duhan
