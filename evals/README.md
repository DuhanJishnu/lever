# Evals

30 tasks (15 dev / 15 held-out, see `SPLIT.md`) with hidden tests.
Categories: bugfix 10, feature 8, refactor 5, multi-file 4, write-tests 3.

## Layout per task

```
<id>/repo/            # starting code the agent sees
<id>/task.md          # issue-style description (the prompt)
<id>/hidden_tests/    # grading only; staged into the workspace at grade time
<id>/meta.json        # {id, category, difficulty, test_cmd, timeout, trap?}
<id>/solution.patch   # reference solution (git-applyable); CI checks it
```

## Commands

```powershell
uv sync --group dev

# 1. Validate tasks (FAIL before patch, PASS 3x after) — also runs in CI
uv run python evals/validate_tasks.py

# 2. Plumbing dry-run (FakeProvider; expect pass=0, proves runner shape)
uv run python evals/runner.py --tasks b01 b02 --seeds 1 --dry-run --out evals/results/smoke.jsonl

# 3. Real B0 run: 30 tasks x 3 seeds (needs GEMINI_API_KEY; costs money)
uv run python evals/runner.py --seeds 3 --jobs 2 --out evals/results/b0.jsonl

# 4. Analyze (table + bootstrap CIs + charts)
uv run python evals/analyze.py --results evals/results/b0.jsonl --charts
```

Backends: `--backend auto` (default) uses Docker `lever-eval` image
(`evals/Dockerfile`; `docker build -t lever-eval evals/`) when the daemon
responds, else local subprocess. Docker Desktop still pending on this machine.
Cost: `cost_usd` stays null unless rates are supplied — tokens are truth.
