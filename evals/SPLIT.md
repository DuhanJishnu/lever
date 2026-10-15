# Eval split: 15 dev / 15 held-out (decided before any tuning)

Rule: iterate freely against **dev**. Touch **held-out** ONLY for final reports
(Phase 5). Tuning on held-out invalidates the headline claim.

## Dev (15) — tune against these

b01, b02, b03, b04, b05, f01, f02, f03, f04, r01, r02, r03, m01, m02, t01

## Held-out (15) — final report only

b06, b07, b08, b09, b10, f05, f06, f07, f08, r04, r05, m03, m04, t02, t03

## Dev-extended / calibration (6) — added Oct 2026, dev only, never held-out

x01, x02, x03, x04, m05, m06

Per the plan's own calibration rule (rebalance when B0 ≈ 100%): the original
30 could not discriminate harness rungs on a strong model, so these 6 target
edit-stress (whitespace-shifted quotes, typo'd quotes, multi-match blocks),
long-file reads, and hard multi-file reasoning. They may join ladders but
never the held-out report.
