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

## m02 saga (local, $0) — the ladder working as intended| run | b0 | b1 | b2 | b3 |
|---|---|---|---|---|
| first | fail (hallucinated verify) | fail (grep broke) | **PASS** (ambiguity → `replace_all`) | fail (1-step: single-quote fence) |
| second | **PASS** | fail | fail | **PASS** (after quote fix) |

- B1's ambiguity error → model sets `replace_all=true` → m02 solved. The
  error-message design working exactly as specified.
- B3's first signal: single-quote fences unparsed → 1-step stop; after the
  parser fix, 7-step pass. (Map contribution unproven at 2-file scale —
  the pass used reads + edits, map presence only.)
- Every config has now solved m02 at least once except b1 (0/2) — pure
  small-model variance, not a ranking.
- **Grep path bug (all configs)**: `relative_to` crashed on relative roots
  (runner shape; unit tests used absolute tmp paths). Fixed + regression test.
  This bug alone killed two runs' verification steps — a reminder that red
  eval traces find harness bugs unit tests miss.

## b01 x 5 real seeds (local, $0) -- first honest local table

Raw JSONL is temp (see learning log); the committed record is this table.

| config | pass@1 | steps | tok/run | notes |
|---|---|---|---|---|
| b0 | 0.20 | 3.6 | 2138 | lean clean stops |
| b1 | 0.60 | 10.6 | 20892 | 3 passes + one 40-step thrash |
| b2 | 0.60 | 10.4 | 21186 | same shape (one thrash) |
| b3 | 0.00 | 3.0 | 1873 | all stop in 3 steps; map early give-up unproven |
| b8 | 0.00 | 3.0 | 1873 | same trajectories as b3; guard silent (nothing to catch) |

B8 live proof pending: b8 seeds 5-9 hunting a thrash-cut. Mechanism proven by
scripted tests; KEEP on mechanism meanwhile.

## B4 local pilot (14 Oct 2026) -- b01/b02 x all configs, up to 6 seeds

b4 == b3 on every aggregate (identical tokens/steps): masking is a no-op
below 7 tool results, and no b4 run went long. Mechanism proven instead by
`test_loop_masks_old_observations` (8 scripted turns: provider-bound history
shows elided markers, events keep full text).

**Decision: KEEP on mechanism, UNMEASURED live.** Masking only matters on
long histories; local runs are too short to engage it. The honest B4 test
needs a 15+ step run under b4 (or the Gemini matrix, where histories run
longer). No-harm proven: b4 never diverges from b3.

## B5 local pilot (14 Oct 2026) -- b02 x all configs, 2 seeds

b5 == b4 == b3 == b8 everywhere (short-run no-op, as designed): no run
exceeded 8 steps, far below the 70%-of-60k tripwire (~42k est tokens vs
~2-6k observed). Compaction cannot fire on toy tasks -- its test is the
deterministic integration suite, which proves pinning, summarization shape,
event emission, and the no-op case.

Notable side observation: b1 went 2/2 on b02 (first b02 wins anywhere) --
small-model variance cuts both ways.

**Decision: KEEP on mechanism, UNMEASURED live.** The honest B5 test is a
100k+ history (per the plan's own acceptance); none of our tasks produce
one. On real long runs the tripwire + event + UI meter path is fully wired.

## B6 local pilot (14 Oct 2026) -- b01/b02 x all 7 configs: mechanism PROVEN live

b01-b6 ran 19 steps (vs 2-4 elsewhere): model claimed done on an UNCHANGED
file -> verify_tests ran pytest -> FAILED (exit 2, SyntaxError) -> trimmed
report fed back -> 15 more turns of genuine varied recovery (syntax-gate
reverts, miss reports, rewrites). Without verify it would have stopped at
turn 4 with a lie. Outcome still fail (4B too weak + literal-\n pathology
below), but this is the first rung whose MECHANISM is demonstrated live,
not just scripted.

Failure taxonomy addition: the model writes literal backslash-n instead of
newlines inside single-quoted fence args, producing one-line files that trip
the syntax gate forever. Fix: single-quoted values now unescape with JSON
semantics (unknown escapes stay literal for paths). Fourth fence shape
covered by the same collect-from-traces rule.

**Decision: KEEP, mechanism proven live.** B6 is the first rung that changes
run SHAPE observably (19 steps vs 4) rather than just passing/failing.

## B7 local pilot (14 Oct 2026) -- b01/b02 x all 8 configs: planner adopted, todo ignored

b7: 0.00 both tasks. Mechanism split: the model visibly follows the v2
WORKFLOW shape (numbered EXPLORE/PLAN/EDIT/VERIFY prose, plan-first reads)
but NEVER calls the `todo` tool -- scratchpad mechanism unexercised. Prompt
adherence is partial: structure yes, tool no.

Fence coverage grows again (all from red traces): backtick-quoted kwarg
values, positional+kwarg-tail mixes, and unambiguous key abbreviations
(old -> old_str; ambiguous/unknown rejected). Fifth and sixth shapes.

**Decision: KEEP on mechanism, PARTIAL live.** Workflow shape adopted;
scratchpad and outcome unproven. The planner delta needs a model that uses
tools-as-instructed (Gemini pilots) or a stronger local model.

## Calibration pilot (14 Oct 2026) -- x01-x04/m05-m06 x b0/b1, local, $0

| config | pass@1 | editfail | notes |
|---|---|---|---|
| b0 | 0.67 (4/6) | 13 | m05/x01/x02/x04 pass; m06/x03 fail |
| b1 | 0.50 (3/6) | 11 | m05/x01/x02 pass; rest fail |
| paired | d -0.17 | -- | noise at n=6; direction meaningless |

Calibration SUCCEEDS on its own terms: edit failures 13 vs 11 (both
nonzero -- the original 30 showed 0 everywhere), mixed outcomes, and a 27-step
exploration (x03 b0). B0 sits at 67% here vs 100% on the originals: headroom
for rungs to show. Pass deltas on a flappy 4B model remain noise; the
discrimination that matters (edit-failure recovery paths firing) is now
measurable, which is exactly what B1 claims to improve. These 6 join all
future local ladders; Gemini pilots will tell the pass story.
