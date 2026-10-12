# Lever: Implementation Plan

> **Lever** is a coding-agent harness that makes a cheap, weaker model (Gemini Flash-tier) perform like a stronger one, using context engineering, tolerant tools, verification loops, and policies, and *proves it with numbers*.
>
> (Name is a placeholder. "Lever" = leverage a weak model. Rename freely.)

Start: Mon 12 Oct 2026 · Target public release: ~2 Dec 2026 · Owner: Jishnu

---

## 0. How to use this document

1. Read sections 1-4 once. They are your "do not forget what I'm building" anchor.
2. Work phase by phase (section 6). Each phase has tasks, an acceptance test, and pitfalls. **Do not start a phase until the previous acceptance test passes.**
3. Tick checkboxes in section 12 daily. Re-read section 1 whenever you feel lost.
4. When stuck, jump to the matching resources in section 11 (referenced as `[S#]`).

---

## 1. North star (never forget this)

**The claim you will prove:**

> "With the Lever harness, Gemini [model] solves X% of coding tasks versus Y% with a bare agent loop, using Z% fewer tokens, measured on held-out tasks with confidence intervals."

Everything you build must either (a) improve that number, (b) measure it honestly, or (c) make it demonstrable (UI, README, demo). If a task does none of these, skip it.

**Non-goals (do NOT build these):**
- Local-model serving itself (you run llama-server; Lever only speaks to its
  OpenAI-compatible endpoint for $0 dev runs — Gemini stays the claims model).
- A terminal TUI (you chose a web UI; a tiny headless CLI is enough).
- A plugin marketplace, auth/multi-user, billing, or cloud deployment.
- LSP integration, multi-provider support beyond the interface, or fancy theming.

**Definition of done (the project is "10/10" only if ALL are true):**
- [ ] Public GitHub repo with README whose first screen shows the results table + chart
- [ ] Eval suite: 30 custom tasks (15 dev / 15 held-out) with hidden tests, plus (stretch) a 40-50 task SWE-bench Lite subset
- [ ] Ablation ladder B0 to B8 run with 3 seeds each, with bootstrap confidence intervals
- [ ] Web UI: live chat, diff viewer, approval prompts, context-budget meter, session replay, eval dashboard
- [ ] Event-sourced sessions (resume, fork, replay work)
- [ ] Policy layer (approvals, cost budget, stateful rule)
- [ ] 2-minute demo video + a blog post that includes what did NOT work
- [ ] At least one upstream contribution or open PR (Omnigent or similar) *(stretch but valuable)*

---

## 2. Architecture

```
 Web UI (React)      CLI / API (Typer)       Eval runner
      \                   |                    /
       +------- SSE events / REST ------------+
                          |
 +------------------- Harness core (FastAPI, asyncio) -------------------+
 |  Context engine   | Agent loop     | Policy layer                      |
 |  (repo map,       | (plan-act-     | (approvals, cost budget,          |
 |   compaction)     |  verify)       |  loop guard)                      |
 |  Tool runtime     | Provider       | Session store                     |
 |  (read/edit/      | adapter        | (event log, SQLite)               |
 |   grep/bash)      | (Gemini)       |                                   |
 |  MCP client       | Trace emitter  | Prompt registry                   |
 +-------------------------------------------------------------------+
        |                   |                     |
   Docker sandbox       Gemini API         Workspace (git worktree)
```

### Key design decisions (and why)

| # | Decision | Why it matters |
|---|---|---|
| 1 | **Event sourcing**: every model call, tool call, approval is an immutable event | Resume, fork, undo, replay, and evals all come from one mechanism |
| 2 | **Everything is a toggle in `HarnessConfig`** | Ablation study becomes just running configs B0..B8 |
| 3 | **Context is a managed object** with tiers: pinned / working-set / history / observations | Each tier gets its own shrink policy and token accounting |
| 4 | **Tools return model-friendly errors** (what went wrong + how to fix) | Weak models recover from good errors, die on stack traces |
| 5 | **Policies live in code, not prompts** | Same idea as Omnigent's control layer |
| 6 | **Git worktree per session + checkpoints** | Safe, undoable edits; clean diffs for the UI |
| 7 | **Docker sandbox, no network by default** | Safe bash/test execution; reproducible evals |
| 8 | **Record/replay LLM responses in tests** | Deterministic, free CI; cheap re-runs |
| 9 | **Fixed thinking budget and temperature across configs** | Fair comparisons: only the harness changes |

---

## 3. Tech stack

| Layer | Choice |
|---|---|
| Language/runtime | Python 3.12, `uv` for env/deps, asyncio |
| API/server | FastAPI, Pydantic v2, `sse-starlette` for SSE |
| Model access | Your own `Provider` protocol; Gemini via the `google-genai` SDK **or** its OpenAI-compatible endpoint |
| Storage | SQLite (WAL mode) with an append-only `events` table |
| Code intelligence | `tree-sitter` (+ language grammars) for repo map and syntax checks |
| Sandbox | `docker` Python SDK |
| Frontend | React + Vite + TypeScript + Tailwind, `@monaco-editor/react` (diff), Recharts, TanStack Query |
| Observability | OpenTelemetry spans + your own trace viewer page |
| Eval | pytest inside Docker, JSONL results, pandas + scipy (bootstrap CIs), matplotlib for README charts |
| Quality | `ruff`, `mypy`, `pytest`, GitHub Actions |
| Extras | MCP Python SDK, Typer (headless CLI) |

---

## 4. Repo layout

```
lever/
  pyproject.toml
  README.md
  src/lever/
    core/        events.py  config.py  loop.py  session.py
    providers/   base.py  gemini.py  fake.py        # fake = scripted/replay for tests
    tools/       base.py  fs.py  edit.py  grep.py  bash.py  mcp.py
    context/     budget.py  repomap.py  masking.py  compaction.py
    policy/      engine.py  rules.py
    sandbox/     docker.py
    store/       sqlite.py  schema.sql
    prompts/     registry.py  v1/  v2/              # versioned prompt files (.md)
    server/      app.py  routes.py  sse.py
    cli.py
  evals/
    tasks/       <task_id>/{repo/, task.md, hidden_tests/, meta.json}
    runner.py  analyze.py  report.py
    results/     *.jsonl
  web/           (React app)
  tests/
  docs/          (design notes, blog draft, screenshots)
```

---

## 5. Core data models (write these first)

```python
# core/events.py
from pydantic import BaseModel
from typing import Literal, Any

class Event(BaseModel):
    id: int | None = None
    session_id: str
    seq: int
    ts: float
    type: Literal[
        "user_message", "model_request", "model_response",
        "tool_call", "tool_result", "approval_request",
        "approval_decision", "context_compacted", "policy_block",
        "checkpoint", "error", "session_end",
    ]
    data: dict[str, Any]          # payload; always JSON-serializable
```

```python
# core/config.py
from pydantic import BaseModel

class HarnessConfig(BaseModel):
    model: str = "gemini-<flash-tier>"      # check current model list
    temperature: float = 0.2
    thinking_budget: int | None = None      # keep IDENTICAL across ablations
    max_steps: int = 40
    context_budget_tokens: int = 60_000

    # ---- feature toggles (each is one ablation step) ----
    tolerant_edit: bool = False
    repo_map: bool = False
    output_truncation: bool = False
    observation_masking: bool = False
    compaction: bool = False
    verify_loop: bool = False
    planner_prompt: bool = False
    loop_guard: bool = False
    best_of_n: int = 1
    prompt_version: str = "v1"
```

```python
# providers/base.py
from typing import Protocol

class Provider(Protocol):
    async def generate(self, messages: list[dict], tools: list[dict],
                       config: "HarnessConfig") -> "ModelResponse": ...
    def count_tokens(self, messages: list[dict]) -> int: ...
```

---

## 6. Phases (step-by-step)

### Phase 0: Foundations (12-14 Oct, 3 days)

**Goal:** repo, tooling, event schema, one working Gemini call, logged as events.

Tasks
- [ ] Create repo, `uv init`, add ruff/mypy/pytest, set up GitHub Actions (lint + test).
- [ ] Create a Gemini API key; make one raw call from a script. Confirm **function calling works across multiple turns** (this is the riskiest API detail; check how the SDK expects tool results and any thinking-related fields to be replayed in history) `[S10, S11]`.
- [ ] Implement `Provider` protocol, `GeminiProvider`, and `FakeProvider` (returns scripted responses).
- [ ] Implement SQLite event store: `append(event)`, `read(session_id)`.
- [ ] Add an on-disk **response cache** keyed by hash of (model, messages, tools, config). Cache hits skip the API call. This saves money for the whole project.
- [ ] Write the `HarnessConfig` and `Event` models above.

Acceptance test: a script sends "say hi" through the provider; the request + response appear as events in SQLite; a second run hits the cache.

Pitfalls: leaking your API key into git (use `.env` + `.gitignore`); forgetting rate limits (add retry with exponential backoff now).

---

### Phase 1: Naive agent = baseline B0 (15-21 Oct, Week 1)

**Goal:** a plain agent loop with 5 tools. Deliberately naive, because this is your *baseline*. Do not add clever features yet.

Tasks
- [ ] **Tools** (`tools/`): `read_file(path)`, `write_file(path, content)`, `edit_file(path, old_str, new_str)` (exact match only for now), `grep(pattern, path)`, `bash(cmd, timeout)`. Define JSON schemas; give each tool a clear description.
- [ ] **Tools are bound to the session, not globals**: factory `create_tools(session)` builds the registry from that session's workspace/sandbox handle (dependency injection). Tools never import environment state directly. This enables parallel eval runs, unit-testing tools against a temp dir, and clean lifecycle management.
- [ ] **Path safety**: all paths resolved inside the workspace root; reject `..` escapes.
- [ ] **Agent loop** (`core/loop.py`):
  ```
  session.open()                          # harness owns lifecycle; try/finally close
  try:
      tools = create_tools(session)       # bound to THIS session's environment
      messages = fresh_context(task)      # no history from previous tasks (isolation)
      trace = []
      for step in range(max_steps):
          guard = guardrails.check(state) # structural checks run BEFORE each model call
          if guard.stop: break            # record stopped_by="guardrail"
          resp = provider.generate(messages, tools)
          emit(model_response)
          track context_size per iteration (for trace + context-rot analysis)
          if no tool calls: break         # stopped_by="model"
          for call in resp.tool_calls:
              result = tools.run(call)    # emit tool_call / tool_result
              messages.append(tool_result)
      # stopped_by is always recorded: "model" | "guardrail" | "max_steps"
  finally:
      session.close()                     # ALWAYS, even on error
  ```
- [ ] **Session**: workspace = a git worktree/copy of the repo; session id; all steps emit events.
- [ ] **Headless CLI** (Typer): `lever run --repo ./path --task "fix failing test" --config b0.yaml`.
- [ ] Print events as JSON lines (this becomes your "event stream" for later integrations).

Acceptance test: on a toy repo with a one-line bug and a failing test, the agent reads, edits, and (when you run tests) fixes it end-to-end at least once. Replay of the session from SQLite reproduces the same event sequence.

Pitfalls: unbounded tool output (cap at, say, 20k chars even in B0 so runs don't explode, and document that cap as part of B0); infinite loops (`max_steps` is part of B0).

Resources: `[S1, S2, S3, S12, S13]`. Build this in the spirit of mini-swe-agent: tiny and readable.

---

### Phase 2: Eval harness FIRST (22-28 Oct, Week 2)

**Goal:** a trustworthy measuring stick *before* you optimize. Without it, no improvement claim is credible `[S20, S21]`.

Task design (30 tasks)
- Categories: bugfix (10), feature add (8), refactor (5), multi-file change (4), write-tests (3).
- Mostly Python (simple Docker image, pytest), a few JS/TS if time allows.
- Each task folder:
  ```
  task_id/
    repo/            # starting code (small: 5-40 files)
    task.md          # issue-style description (what the user would say)
    hidden_tests/    # NEVER shown to the agent; copied in only at grading time
    meta.json        # {category, difficulty, test_cmd, timeout, trap?}
  ```
- **Trap cases**: for a subset of tasks, record in `meta.json` the `"trap"` — the plausible-but-wrong answer a weak model typically gives (e.g. editing the wrong file, Sydney-instead-of-Canberra-style misdirection). The runner reports `fell_for_trap` per run; the analysis reports trap rate per config. A config that reduces trap rate is genuinely steering the model, not just getting lucky.
- **Avoid contamination**: don't use famous GitHub issues verbatim; write your own repos or mutate small OSS code so the model can't recall solutions.
- **Dev/held-out split**: 15 dev tasks (you may look at failures and tune against these), 15 held-out (touch ONLY for final reports). Decide the split now and write it in `evals/SPLIT.md`.

Runner
- [ ] `runner.py`: for each (task, config, seed): start Docker container, copy repo, run agent, copy in hidden tests, run `test_cmd`, record pass/fail.
- [ ] Record per run: pass, tokens in/out, steps, wall time, estimated cost, tool-error count, edit-failure count, compaction count, final diff, session id, **stopped_by** (`model`/`guardrail`/`max_steps`), **trap rate** (on trap-tagged tasks), per-iteration context sizes.
- [ ] Append results as JSONL. Make the runner **resumable** (skip finished runs) and **parallel** (a small asyncio semaphore; respect API rate limits).
- [ ] Validate tasks: every task must FAIL on the starting repo and PASS with a reference solution. Store `solution.patch` and check it in CI.

Analysis
- [ ] `analyze.py`: pass@1 per config (mean over 3 seeds), **bootstrap 95% CI** `[S22]`, paired per-task comparison versus the previous config, token/cost averages.
- [ ] Charts: bar chart of config vs pass rate with CI; per-task heatmap (task × config).

Acceptance test: B0 runs on all 30 tasks × 3 seeds, producing a results table. Reference solutions pass all 30 tasks.

Pitfalls: flaky tests (run reference solution 3 times); tasks too easy or too hard (aim for B0 at roughly 20-40%; if B0 gets 0% or 90%, you can't show improvement, so rebalance tasks).

---

### Phase 3: Harness engineering (29 Oct to 11 Nov, Weeks 3-4)

**Rule: add ONE feature at a time. After each, run the dev tasks, record the delta, keep or discard it.** Each feature is a toggle in `HarnessConfig`. This is the ablation ladder.

| Config | Adds | Primary hypothesis |
|---|---|---|
| B0 | Bare loop | Baseline |
| B1 | Tolerant edit tool | Fewer failed edits |
| B2 | Output truncation (+ ranged `read_file`) | Less context waste |
| B3 | Repo map | Finds the right files faster |
| B4 | Observation masking | Longer effective horizon |
| B5 | Compaction + pinned memory | Survives long tasks |
| B6 | Verify loop (auto-run tests) | Catches wrong "done" claims |
| B7 | Planner prompt + scratchpad | Better decomposition |
| B8 | Loop guard (+ optional best-of-N) | Fewer stuck runs |

#### 3.1 Tolerant edit tool (B1) `[S5, S6, S3]`
Matching cascade, stop at the first success:
1. Exact match of `old_str`.
2. Match ignoring trailing whitespace and normalized indentation.
3. Line-based fuzzy match: slide a window of the same line count over the file; use `difflib.SequenceMatcher` ratio ≥ 0.9; apply only if exactly one candidate.
4. Fail with a **structured error**: "old_str not found. Closest match at lines 41-47 (similarity 0.82): <snippet>. Re-read the file and retry."
- If multiple matches: error with line numbers of each; suggest more context or `replace_all`.
- After a successful edit: **syntax check** (tree-sitter parse or `python -m py_compile`). If it breaks syntax, revert and tell the model exactly where.
- Return a short unified diff of what changed, not the whole file.

#### 3.2 Output truncation and ranged reads (B2) `[S8, S9]`
- `read_file(path, start_line, end_line)`; default returns the first N lines plus a note "file has 812 lines; call again with a range".
- Truncate tool output to head + tail with an explicit marker `[... 340 lines omitted ...]`.
- Grep returns at most N matches with file:line and a one-line context.

#### 3.3 Repo map (B3) `[S4, S14]`
1. Parse each source file with tree-sitter; extract definitions (classes, functions) and references.
2. Build a graph: file A → file B if A references a symbol defined in B.
3. Rank files with PageRank, personalized toward files mentioned in the task or already touched.
4. Render as compact text (file → key signatures). **Binary-search the number of entries** to fit a token budget (e.g., 1.5k tokens).
5. Put the map in the context's pinned tier; refresh it after edits.

#### 3.4 Observation masking (B4) `[S9, S8]`
- Keep the last K (e.g., 6) tool results in full; replace older ones with a one-line placeholder: `[output of grep "foo" elided (212 lines). Re-run if needed.]`
- Never mask the assistant's own reasoning/tool calls (cheap and important for coherence).
- Keep tool-call/tool-response pairing valid for the Gemini API (a response must still follow its call).

#### 3.5 Compaction with pinned memory (B5) `[S8, S9, S15]`
- Trigger at ~70% of `context_budget_tokens` (use `count_tokens`).
- Pinned tier is **never** compacted: task statement, constraints, repo map, current plan.
- Compaction ladder: (1) masking, (2) truncate the biggest outputs, (3) LLM summary of old history into a fixed-schema state note:
  ```
  GOAL / DECISIONS MADE / FILES MODIFIED (with 1-line why) / TEST STATUS / OPEN ISSUES / NEXT STEPS
  ```
- Emit a `context_compacted` event with before/after tokens (your UI meter uses this).
- Test: craft a long task that needs 100k+ tokens of history; B4 should degrade, B5 should survive.

#### 3.6 Verify loop (B6) `[S3, S16]`
- When the model stops calling tools (claims done), run the project's test command in the sandbox.
- Feed back a *trimmed* failure report (first failing test + last ~40 lines); let the model continue. Cap at 3 verify rounds.
- If no test command exists, run a syntax/lint check instead.
- Careful: hidden tests are for grading only. The verify loop must use tests the agent can see (the repo's own tests, or ones the agent wrote).
- **Trace-based semantic checks** (beyond pass/fail): inspect the run trace before accepting "done" — e.g. did any iteration invoke the test command? Do files referenced in the final answer exist in the workspace? Unverified claims ("tests pass" with no test run in trace) are sent back to the model as feedback. This is the **guardrails-vs-verify split**: guardrails enforce structure (can't be bypassed), verify checks meaning (catches hallucinations).
- **Tool hooks**: critical tools emit success signals the harness subscribes to (e.g. edit tool reports files changed, test tool reports pass/fail) rather than trusting the model's prose summary. Verification reads hooks + trace, not the chat text.

#### 3.7 Planner prompt and scratchpad (B7) `[S1, S7, S17]`
- Versioned prompts in `prompts/vN/*.md` (system prompt split into sections: role, workflow, tool-use rules, edit rules, done criteria).
- Workflow section: *explore → plan (write PLAN to a scratchpad/todo tool) → edit → verify → summarize*.
- Add 2-3 short worked examples of correct tool use (few-shot).
- The plan lives in the pinned tier so it survives compaction.
- Use the prompt registry to A/B prompt versions; log `prompt_version` in every run.

#### 3.8 Loop guard (B8) `[S3, S16]`
- **Composable guardrail functions**: each guard is a small function
  `guard(state) -> continue | stop(reason)` (state = iterations, messages/context size,
  tool-call history, cost so far). Guards compose: run all before each model call,
  first `stop` wins and is recorded as `stopped_by`. Ship at minimum: `max_iterations`,
  `max_context_messages`, `no_repeated_failed_calls(3)`, `budget_exceeded`, `time_limit`.
- Hash `(tool, normalized args)`; if the same call repeats 3×, inject a nudge ("You already did this. Try a different approach.").
- After 2 nudges: force a re-plan turn (summarize what failed, propose new approach).
- Hard stop at `max_steps` with a clean failure event.
- Optional: `best_of_n` with test-based selection. Report its cost multiplier honestly.

Acceptance test for Phase 3: for every feature, a row in `docs/ablations.md` with dev-set pass rate, tokens, and a keep/discard decision with a one-line reason. Aim for a monotone-ish story, but **document features that didn't help**.

Pitfalls: changing two things at once (you won't know what worked); tuning on held-out tasks (don't); forgetting the same thinking budget/temperature in every config.

---

### Phase 4: Policy layer and web app (12-18 Nov, Week 5)

#### 4.1 Policy engine (`policy/`) `[S18]`
- Rule interface: `evaluate(event_history, proposed_call) -> allow | deny(reason) | ask`.
- Rules to ship:
  - Deny writes outside the workspace.
  - Ask before bash commands outside an allowlist (`pytest`, `ls`, `cat`, `git diff`, etc.).
  - **Cost budget**: pause and ask after every $X (or N tokens).
  - **Stateful rule**: after any `pip install` / `npm install`, require approval before `git push` or network access.
- Every decision becomes an event (`policy_block`, `approval_request`, `approval_decision`).

#### 4.2 Server `[S23, S24]`
- REST: `POST /sessions`, `POST /sessions/{id}/messages`, `POST /sessions/{id}/approvals/{req_id}`, `GET /sessions`, `GET /sessions/{id}/events`, `POST /sessions/{id}/fork?at_seq=N`.
- SSE: `GET /sessions/{id}/stream` pushes events live.
- The agent loop runs as a background asyncio task; approvals resolve an `asyncio.Future`.

#### 4.3 Frontend pages (`web/`) `[S25, S26]`
1. **Run view**: chat transcript, live event timeline, Monaco diff viewer for changed files, approval modal.
2. **Context inspector**: stacked bar (pinned / working-set / history / observations) vs budget; markers where compaction fired.
3. **Sessions**: list, replay (scrub through events), fork from any step.
4. **Eval dashboard**: config vs pass-rate with CIs, per-task heatmap, cost vs accuracy scatter.

Acceptance test: start a task from the browser, watch it stream, approve a bash command, see the diff, replay the finished session, open the eval dashboard populated from `evals/results/`.

Pitfalls: polishing CSS for days (use Tailwind defaults; the *context inspector* and *eval dashboard* are the standout screens, so spend time there).

---

### Phase 5: Credibility run (19-25 Nov, Week 6)

- [ ] Freeze the harness. Tag `v1.0-eval`.
- [ ] Run **held-out** tasks for B0 and the final config (and the full ladder if budget allows), 3 seeds each.
- [ ] Stretch: run a **40-50 instance SWE-bench Lite subset** for B0 vs final config `[S19]`. This needs Docker images and time; do it only if the custom eval is done and clean. If infrastructure fights you for more than 2 days, drop it and say so in the write-up.
- [ ] Generate final charts and tables; compute CIs and paired differences.
- [ ] Write `docs/results.md`: what improved, by how much, what *didn't* help, cost tradeoffs, failure analysis (categorize 15-20 failures: wrong file, bad edit, gave up early, loop, test misunderstanding...).

Acceptance test: you can state the headline claim from section 1 with real numbers.

---

### Phase 6: Ecosystem and release (26 Nov to 2 Dec, Week 7)

- [ ] **MCP client** (`tools/mcp.py`): connect to one MCP server (e.g., filesystem or fetch) and expose its tools; add one eval-neutral demo `[S27]`.
- [ ] **Event-stream adapter**: ensure `lever run --json` emits a stable JSON-lines protocol (messages/files in, text stream + tool calls out). Write a small adapter spec so an Omnigent-style meta-harness could wrap Lever `[S28, S29]`.
- [ ] **Upstream contribution**: pick one concrete, small thing (a docs fix, a new example, an adapter for Lever, a bug fix) and open a PR to Omnigent or another agent-infra repo.
- [ ] README: results table + chart first, then a 30-second quickstart, architecture diagram, design decisions, how to reproduce evals.
- [ ] 2-minute demo video (screen record: task, live run, diff, context meter, eval dashboard).
- [ ] Blog post (see outline in section 10).
- [ ] Clean up: tag `v1.0`, add LICENSE (Apache-2.0 or MIT), `make eval` / `make dev` commands.

---

## 7. Eval methodology (read before Phase 2)

- **Primary metric:** pass@1 averaged over 3 seeds. Hidden tests decide pass/fail; no partial credit.
- **Secondary:** tokens/task, steps/task, wall time, estimated cost, edit-failure rate, tool-error rate, stuck-run rate, **trap rate** (on trap-tagged tasks), **stopped-by breakdown** (model/guardrail/max_steps — diagnoses whether failures are giving-up vs guardrail-stopped).
- **Statistics:** bootstrap 95% CIs over tasks; for config-vs-config claims, use a *paired* analysis (same tasks) `[S22]`. With only 15 held-out tasks, differences under ~10 points are probably noise. Say so honestly.
- **Fairness:** same model, temperature, thinking budget, max steps, token cap on tool output *definition* (B0 has a coarse one), and same Docker image across configs.
- **Seeds:** Gemini isn't fully deterministic even at low temperature, so run each (task, config) 3 times and report the mean.
- **Cost control:** estimate tokens before a full run (`tasks × configs × seeds × avg tokens`); use the response cache; run the dev set during development and the held-out set only at the end.

---

## 8. Weekly schedule

| Dates | Phase | Milestone |
|---|---|---|
| 12-14 Oct | 0 | Provider + event store + cache working |
| 15-21 Oct | 1 | B0 agent solves a toy task end-to-end |
| 22-28 Oct | 2 | 30 tasks + runner + B0 numbers |
| 29 Oct to 4 Nov | 3a | B1-B4 measured |
| 5-11 Nov | 3b | B5-B8 measured, ablation doc |
| 12-18 Nov | 4 | Policy layer + web UI |
| 19-25 Nov | 5 | Held-out results (+ SWE-bench subset) |
| 26 Nov to 2 Dec | 6 | MCP, adapter, PR, README, video, blog |
| December | Buffer | Apply, polish, interview prep with this project |

### If you fall behind: cut list (cut in this order)
1. SWE-bench subset
2. Upstream PR (keep the adapter spec)
3. MCP client
4. Best-of-N and fork UI
5. Frontend polish (keep context inspector + eval dashboard)

**Never cut:** the eval harness, the ablation ladder, the held-out run, or the README results table.

---

## 9. Risk register

| Risk | Likelihood | Mitigation |
|---|---|---|
| API rate limits/costs spike | Medium | Response cache, dev-set-only iteration, batch runs overnight |
| B0 too strong or too weak | Medium | Calibrate tasks in Phase 2 until B0 is ~20-40% |
| Gemini tool-calling quirks (history replay, thinking fields) | Medium | Test multi-turn tool calls in Phase 0; wrap in provider adapter |
| Overfitting to dev tasks | High | Strict held-out discipline; report both dev and held-out |
| Scope creep (UI, MCP) | High | Section 1 non-goals; cut list above |
| Flaky tests/tasks | Medium | Validate with reference solutions 3×; remove flaky tasks |
| Gains are small | Medium | Still publish: an honest negative/mixed result with analysis is valuable. Also report token savings. |

---

## 10. Write-up and resume

### README skeleton
1. One-line pitch + results chart + results table
2. 30-second quickstart (`uv run lever ...`, `docker compose up`)
3. What Lever does (ablation ladder in one table)
4. Architecture diagram + 5 key design decisions
5. How the evals work + how to reproduce
6. Limitations and what didn't work
7. Roadmap (Omnigent-style adapter, more models)

### Blog outline
1. Why harness matters more than you think (weak model, same tasks)
2. The measurement setup (tasks, held-out, CIs)
3. The ladder: what each feature gave (with failures)
4. Surprises and negative results
5. Cost vs accuracy tradeoffs
6. What I'd do next

### Resume bullet templates (fill with real numbers)
- Built **Lever**, an event-sourced coding-agent harness (Python, FastAPI, React) that raised Gemini Flash's pass@1 from **X% to Y%** on held-out tasks while cutting tokens by **Z%**.
- Designed ablation-driven eval framework (30 hidden-test tasks, Docker-isolated, bootstrap CIs) used to measure 8 harness techniques: tolerant edits, repo maps, observation masking, compaction, verify loops.
- Implemented a stateful policy engine (approvals, cost budgets, install-then-push rules) and web UI with session replay, context inspector, and live diffs.

---

## 11. Sources and references

*I compiled these from memory without live browsing. Titles are reliable; URLs may have moved, so if a link fails, search the exact title. Gemini model names and pricing change often, so check the official docs.*

### Agent design and context engineering
- **[S1]** Anthropic, *Building effective agents*: https://www.anthropic.com/research/building-effective-agents. Workflows vs agents, tool design, simplicity first. Read before Phase 1.
- **[S2]** Thorsten Ball, *How to Build an Agent*: https://ampcode.com/how-to-build-an-agent. A working coding agent in ~400 lines. Read during Phase 1.
- **[S3]** *SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering* (Yang et al., 2024), arXiv:2405.15793. The "agent-computer interface" idea is exactly your tool-design thesis. Read before Phase 3.
- **[S4]** Aider docs, *Building a better repository map with tree-sitter*: https://aider.chat/docs/repomap.html. Your repo-map blueprint.
- **[S5]** Aider docs, *Edit formats*: https://aider.chat/docs/more/edit-formats.html. How edit formats affect model reliability.
- **[S6]** Aider, *Unified diffs make GPT-4 Turbo 3X less lazy*: https://aider.chat/docs/unified-diffs.html. A model of "harness change → measured gain" writing.
- **[S7]** Lilian Weng, *LLM Powered Autonomous Agents*: https://lilianweng.github.io/posts/2023-06-23-agent/. Planning, memory, tool-use theory.
- **[S8]** Anthropic Engineering, *Effective context engineering for AI agents*. Search that title on anthropic.com/engineering. Context rot, compaction, notes, sub-agents.
- **[S9]** Manus blog, *Context Engineering for AI Agents: Lessons from Building Manus*: https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus. Practical masking and KV-cache lessons.
- **[S15]** *Lost in the Middle: How Language Models Use Long Contexts* (Liu et al., 2023), arXiv:2307.03172. Why context placement matters (pin important things).
- **[S16]** *ReAct: Synergizing Reasoning and Acting in Language Models* (Yao et al., 2022), arXiv:2210.03629; and *Reflexion* (Shinn et al., 2023), arXiv:2303.11366. Theory for the loop and verify/retry ideas.
- **[S17]** Anthropic docs, *Prompt engineering overview*: https://docs.claude.com/en/docs/build-with-claude/prompt-engineering/overview. Structure, examples, and XML-style sections apply to Gemini prompts too.
- Also search: *"The Complexity Trap: Simple Observation Masking Is as Efficient as LLM Summarization for Agent Context Management"* (JetBrains Research, 2025). Evidence for B4 vs B5 comparisons.

### Reference implementations (read the code when stuck)
- **[S12]** mini-swe-agent: https://github.com/SWE-agent/mini-swe-agent. A ~100-line agent loop; perfect Phase 1 reference.
- **[S13]** opencode: https://github.com/sst/opencode (may have moved orgs; search "opencode github"). Tool set, permissions, session handling.
- **[S14]** Aider source (repo map): https://github.com/Aider-AI/aider, see `repomap.py`.
- Gemini CLI: https://github.com/google-gemini/gemini-cli. A Gemini-based harness to compare against.
- OpenHands: https://github.com/All-Hands-AI/OpenHands and paper arXiv:2407.16741. Sandboxed runtime and event stream architecture.
- Agentless, arXiv:2407.01488. Shows a simple non-agentic pipeline can compete, a useful baseline idea.

### Evals
- **[S19]** SWE-bench (Jimenez et al., 2023), arXiv:2310.06770 and https://www.swebench.com. Harness, Lite/Verified subsets, Docker evaluation setup.
- **[S20]** Hamel Husain, *Your AI Product Needs Evals*: https://hamel.dev/blog/posts/evals/. Practical eval mindset.
- **[S21]** Aider polyglot benchmark and leaderboard: https://aider.chat/docs/leaderboards/. Example of reporting model + edit-format combos.
- **[S22]** *Adding Error Bars to Evals: A Statistical Approach to Language Model Evaluations* (Miller, 2024), arXiv:2411.00640. Use this for your CI/paired-analysis section.

### Gemini API and platform
- **[S10]** Gemini API docs: https://ai.google.dev/gemini-api/docs. Start with quickstart, models list, rate limits.
- **[S11]** Gemini function calling guide (under the docs above) and the *OpenAI compatibility* page: https://ai.google.dev/gemini-api/docs/openai. Also check the token-counting and thinking pages.

### Engineering building blocks
- **[S18]** Martin Fowler, *Event Sourcing*: https://martinfowler.com/eaaDev/EventSourcing.html. Theory for your event log, replay, and fork.
- **[S23]** FastAPI docs: https://fastapi.tiangolo.com and `sse-starlette` on PyPI/GitHub for SSE.
- **[S24]** Python `asyncio` docs (tasks, `Future`, `Semaphore`) for approval flow and parallel eval runs.
- **[S25]** React + Vite docs: https://vite.dev and https://react.dev; `@monaco-editor/react` (DiffEditor) on npm.
- **[S26]** Recharts: https://recharts.org for the dashboard charts.
- tree-sitter: https://tree-sitter.github.io/tree-sitter/ and the `py-tree-sitter` repo for Python bindings.
- Docker SDK for Python: https://docker-py.readthedocs.io. Containers, mounts, timeouts.
- OpenTelemetry docs: https://opentelemetry.io/docs/ (see the GenAI semantic conventions).
- **[S27]** Model Context Protocol: https://modelcontextprotocol.io and the Python SDK repo `modelcontextprotocol/python-sdk`.

### Omnigent / meta-harness context
- **[S28]** Databricks blog, *Introducing Omnigent: A Meta-Harness to Combine, Control and Share Your Agents* (the PDF you uploaded).
- **[S29]** Omnigent: https://github.com/omnigent-ai/omnigent, docs at https://omnigent.ai/, quickstart at https://omnigent.ai/quickstart/install. Read the repo's contribution guide before your PR.

---

## 12. Progress tracker (tick as you go)

**Phase 0**
- [ ] Repo + CI
- [ ] Gemini multi-turn tool call verified
- [ ] Provider, Fake provider, event store, response cache

**Phase 1 (B0)**
- [ ] 5 tools with schemas + path safety
- [ ] Agent loop + sessions + events
- [ ] Headless CLI
- [ ] Toy bug fixed end-to-end; replay works

**Phase 2 (Evals)**
- [ ] 30 tasks written, reference solutions pass, split documented
- [ ] Docker runner (resumable, parallel)
- [ ] Analysis script (CIs, charts)
- [ ] B0 numbers recorded (target 20-40%)

**Phase 3 (Ladder)**
- [ ] B1 tolerant edit
- [ ] B2 truncation + ranged reads
- [ ] B3 repo map
- [ ] B4 observation masking
- [ ] B5 compaction + pinned memory
- [ ] B6 verify loop
- [ ] B7 planner prompt + scratchpad
- [ ] B8 loop guard
- [ ] `docs/ablations.md` complete

**Phase 4**
- [ ] Policy engine + 4 rules
- [ ] REST + SSE server
- [ ] Run view + diff
- [ ] Context inspector
- [ ] Sessions replay/fork
- [ ] Eval dashboard

**Phase 5**
- [ ] Harness frozen, tag created
- [ ] Held-out results (3 seeds)
- [ ] (Stretch) SWE-bench Lite subset
- [ ] `docs/results.md` with failure analysis

**Phase 6**
- [ ] MCP client
- [ ] JSON event-stream adapter spec
- [ ] Upstream PR opened
- [ ] README, demo video, blog post
- [ ] v1.0 released

---

### One-paragraph reminder to paste at the top of every work session

*I am building Lever to prove that a harness can make a weak Gemini model solve more coding tasks, with measured, honest numbers. Eval first, one feature at a time, held-out discipline, and ship the write-up. If it doesn't move the number or help demonstrate it, I skip it.*
