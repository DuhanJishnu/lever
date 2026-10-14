"""Eval analysis: pass@1 + bootstrap 95% CI, paired diffs, charts, markdown table.

Primary metric: pass@1 averaged over seeds, then mean over tasks.
Statistics: bootstrap CIs over tasks; paired per-task diffs for config-vs-config.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path


def load_results(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def task_rates(rows: list[dict], config: str) -> dict[str, float]:
    """Per-task pass rate across seeds for one config."""
    by_task: dict[str, list[int]] = {}
    for r in rows:
        if r["config"] == config:
            by_task.setdefault(r["task"], []).append(1 if r["pass"] else 0)
    return {t: sum(v) / len(v) for t, v in by_task.items()}


def bootstrap_ci(values: list[float], n: int = 2000, seed: int = 0) -> tuple[float, float]:
    rng = random.Random(seed)
    k = len(values)
    if k == 0:
        return (0.0, 0.0)
    means = sorted(
        sum(rng.choice(values) for _ in range(k)) / k for _ in range(n)
    )
    return means[int(0.025 * n)], means[int(0.975 * n)]


def summarize(rows: list[dict]) -> dict[str, dict]:
    configs = sorted({r["config"] for r in rows})
    errors = [r for r in rows if r.get("error")]
    rows = [r for r in rows if not r.get("error")]  # error rows never count as fails
    out: dict[str, dict] = {}
    for c in configs:
        rates = task_rates(rows, c)
        vals = list(rates.values())
        mean = sum(vals) / len(vals) if vals else 0.0
        lo, hi = bootstrap_ci(vals)
        cr = [r for r in rows if r["config"] == c]
        out[c] = {
            "tasks": len(vals),
            "pass_at_1": round(mean, 3),
            "ci95": [round(lo, 3), round(hi, 3)],
            "mean_tokens": round(sum(r["tokens_in"] + r["tokens_out"] for r in cr)
                                 / max(1, len(cr)), 1),
            "mean_steps": round(sum(r["steps"] for r in cr) / max(1, len(cr)), 1),
            "mean_wall_s": round(sum(r["wall_s"] for r in cr) / max(1, len(cr)), 1),
            "trap_rate": _rate([r["fell_for_trap"] for r in cr
                                if r["fell_for_trap"] is not None]),
            "stopped_by": _counts([r["stopped_by"] for r in cr]),
            "edit_failures": sum(r["edit_failures"] for r in cr),
            "tool_errors": sum(r["tool_errors"] for r in cr),
            "n_errors": sum(1 for r in errors if r["config"] == c),
        }
    # Paired diffs vs previous config (sorted order): same tasks only.
    for i in range(1, len(configs)):
        a, b = configs[i - 1], configs[i]
        ra, rb = task_rates(rows, a), task_rates(rows, b)
        common = sorted(set(ra) & set(rb))
        diffs = [rb[t] - ra[t] for t in common]
        mean = sum(diffs) / len(diffs) if diffs else 0.0
        lo, hi = bootstrap_ci(diffs)
        out[b][f"paired_vs_{a}"] = {
            "delta": round(mean, 3), "ci95": [round(lo, 3), round(hi, 3)],
            "tasks": len(common),
        }
    return out


def _rate(vals: list) -> float | None:
    vals = [v for v in vals if v is not None]
    return round(sum(1 for v in vals if v) / len(vals), 3) if vals else None


def _counts(vals: list[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for v in vals:
        out[v] = out.get(v, 0) + 1
    return out


def heatmap_data(rows: list[dict]) -> tuple[list[str], list[str], list[list[float]]]:
    tasks = sorted({r["task"] for r in rows})
    configs = sorted({r["config"] for r in rows})
    grid = [[task_rates(rows, c).get(t, 0.0) for c in configs] for t in tasks]
    return tasks, configs, grid


def make_charts(rows: list[dict], summary: dict, out_dir: Path) -> list[str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    made = []
    configs = sorted(summary)
    means = [summary[c]["pass_at_1"] for c in configs]
    lo = [summary[c]["ci95"][0] for c in configs]
    hi = [summary[c]["ci95"][1] for c in configs]
    fig, ax = plt.subplots(figsize=(8, 4.5))
    x = range(len(configs))
    ax.bar(list(x), means, yerr=[[m - l for m, l in zip(means, lo)],
                                 [h - m for m, h in zip(means, hi)]],
           capsize=4)
    ax.set_xticks(list(x), configs)
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("pass@1 (95% CI)")
    ax.set_title("Lever eval: config vs pass rate")
    fig.tight_layout()
    p1 = out_dir / "pass_rate.png"
    fig.savefig(p1, dpi=120)
    plt.close(fig)
    made.append(str(p1))

    tasks, cfgs, grid = heatmap_data([r for r in rows if not r.get("error")])
    fig, ax = plt.subplots(figsize=(max(6, len(cfgs)), max(4, 0.35 * len(tasks) + 1)))
    im = ax.imshow(grid, aspect="auto", vmin=0, vmax=1)
    ax.set_xticks(range(len(cfgs)), cfgs)
    ax.set_yticks(range(len(tasks)), tasks)
    ax.set_title("Per-task pass rate (task x config)")
    fig.colorbar(im, ax=ax, label="pass rate")
    fig.tight_layout()
    p2 = out_dir / "heatmap.png"
    fig.savefig(p2, dpi=120)
    plt.close(fig)
    made.append(str(p2))
    return made


def markdown_table(summary: dict) -> str:
    lines = ["| config | tasks | pass@1 | 95% CI | tok/run | steps | wall_s | trap | editfail | toolerr | errors | stopped_by |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for c, s in summary.items():
        lines.append(
            f"| {c} | {s['tasks']} | {s['pass_at_1']:.2f} | "
            f"[{s['ci95'][0]:.2f}, {s['ci95'][1]:.2f}] | {s['mean_tokens']} | "
            f"{s['mean_steps']} | {s['mean_wall_s']} | {s['trap_rate']} | "
            f"{s['edit_failures']} | {s['tool_errors']} | {s['n_errors']} | {s['stopped_by']} |"
        )
        for k, v in s.items():
            if k.startswith("paired_vs_"):
                lines.append(
                    f"|  -> {k} |  | d {v['delta']:+.2f} | "
                    f"[{v['ci95'][0]:+.2f}, {v['ci95'][1]:+.2f}] (n={v['tasks']}) | | | | | | | | | |"
                )
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="Lever eval analysis")
    ap.add_argument("--results", default="evals/results/r1.jsonl")
    ap.add_argument("--out-dir", default="evals/results")
    ap.add_argument("--charts", action="store_true")
    ap.add_argument("--summary-json", default=None)
    args = ap.parse_args()
    rows = load_results(Path(args.results))
    summary = summarize(rows)
    print(markdown_table(summary))
    if args.summary_json:
        Path(args.summary_json).write_text(json.dumps(summary, indent=2),
                                           encoding="utf-8")
    if args.charts:
        made = make_charts(rows, summary, Path(args.out_dir))
        print("charts:", *made)


if __name__ == "__main__":
    main()
