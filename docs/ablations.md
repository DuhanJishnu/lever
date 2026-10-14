# Ablation ladder (dev set; held-out untouched)

Runner: `evals/runner.py`. Analysis: `evals/analyze.py` (pass@1, bootstrap 95%
CI, paired per-task deltas). Raw JSONL: `evals/results/` (gitignored — large,
regenerable; summaries committed here).

## B0 vs B1 (12 Oct 2026) — PARTIAL, 78/90 runs

Matrix: 15 dev tasks × {b0, b1} × 3 seeds. Finished 78; 12 missing
(r03 s2 + r03/b1 ×3 + t01 ×6) — run died on API 429 spending-cap.
Results file: `evals/results/ladder_b0b1.jsonl`
(+ `ladder_b0b1_summary.json`).

| config | tasks | pass@1 | 95% CI | tok/run | steps | trap | editfail | toolerr |
|---|---|---|---|---|---|---|---|---|
| b0 | 13 | 1.00 | [1.00, 1.00] | 21424 | 10.2 | 0.0 | 0 | 8 |
| b1 | 13 | 1.00 | [1.00, 1.00] | 25888 | 10.3 | 0.0 | 0 | 8 |
| paired b1-vs-b0 | | d +0.00 | [+0.00, +0.00] (n=13) | | | | | |

**Decision: KEEP (on mechanism, UNMEASURED on outcome).** Rationale:
- The dev set cannot discriminate B1: B0 already passes 13/13 with ZERO edit
  failures — exact match sufficed everywhere, so the cascade never engaged.
  Ceiling effect: these tasks (written for a weaker model) are too easy for
  3.8-flash, which copies blocks exactly.
- Keep (don't revert) because: unit-tested cascade strictly widens acceptance,
  uniqueness-gated (ambiguous → error, never wrong edit), syntax-revert adds
  safety, and there is no harm signal (steps/wall statistically tied; token gap
  is thinking variance, not the feature).
- To *measure* B1 honestly we need edit-stress tasks (whitespace-shifted,
  typo'd, or multi-match blocks) where B0 verifiably fails. Proposed next.

## Cost incident (12 Oct 2026)

The 90-run matrix at ~21–26k tokens/run (thinking billed) tripped the monthly
spending cap (~₹150) before finishing. Contributing factors: 3 seeds × 15 tasks
× 2 configs launched at once, default thinking (medium), no budget gate.
Guardrails added the same day (`runner.py`): runs default to `--dry-run` ($0);
real runs REQUIRE `--live` plus an estimate + `[y/N]` confirm (or `--yes`).
Rule going forward: pilot 1 task × 1 seed → check tokens → approve matrix.
Open lever: pin `thinking_level` LOW for matrices (verified working, far fewer
thought tokens) — needs your approval since it changes model behavior.

## Local-model ladder (13 Oct 2026) — Gemma 3 4B, $0

Separate tables per provider — NEVER mixed. Local numbers debug the harness;
only Gemini numbers support claims.

| config | tasks | pass@1 | steps | notes |
|---|---|---|---|---|
| b0 (local) | b01, b02 | 0.00 | 1–3 | fence calls unparsed at first; then thrash/stop |
| b1 (local) | b01, b02 | 0.50 | 2–40 | b01 PASS via kwarg fence + exact edit; b02 loops to max_steps |

Findings: (1) B1's first measured win anywhere (b01 local) — via parseable
kwargs, exact rung (cascade itself hasn't fired yet on any model). (2) B1 can
thrash on weak models (b02: 40 steps, 32 edit failures) — tolerance without a
loop guard (B8) multiplies attempts, not success. (3) Local pass rates will stay
near zero; its value is exercising real paths (fence parsing, error rows,
repetition taxonomy) for $0.

## B2 local pilot (14 Oct 2026) — b01/b02 × b0/b1/b2, 1 seed

Results file: `evals/results/local_b1b2.jsonl`.

| config | pass@1 | steps | tok/run | notes |
|---|---|---|---|---|
| b0 | 0.50 | 3.0 | 1939 | b01 passed this time (nondeterminism), b02 failed clean |
| b1 | 0.00 | 23.0 | 51486 | b01 thrashed 40 steps (223s); same task passed yesterday |
| b2 | 0.00 | 4.0 | 2970 | both runs completed, no thrash, no breakage |

**Decision: KEEP on mechanism, UNMEASURED on outcome** (same status as B1).
n=2 on a flappy 4B model cannot discriminate configs — b01/b1 flipped
pass→thrash between days with zero code change. What the pilot DOES show:
truncation+ranged-reads didn't break completion (both b2 runs stop cleanly),
and per-run tokens stay an order of magnitude below thrash runs. Real B2
measurement awaits Gemini pilots.
