"""Task validation: every task FAILS pre-patch and PASSES post-patch (reference solution).

Also run by CI (tests/test_tasks_valid.py). Reference pass is checked 3x to
catch flaky tests. Exit nonzero with a report on any failure.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from runner import grade_local, list_tasks, prepare_workspace, stage_hidden


def check_task(task: dict, repeats: int = 3) -> list[str]:
    problems: list[str] = []
    with tempfile.TemporaryDirectory(prefix="lever_validate_") as tmp:
        ws = Path(tmp) / "ws"
        prepare_workspace(task, ws)
        stage_hidden(task, ws)
        ok, tail = grade_local(ws, task["test_cmd"], int(task.get("timeout", 120)))
        if ok:
            problems.append(f"{task['id']}: PASSES before patch (must FAIL). tail={tail[-300:]}")
            return problems
        patch = Path(task["_dir"]) / "solution.patch"
        proc = subprocess.run(["git", "apply", str(patch)], check=False,
                              cwd=ws, capture_output=True, text=True)
        if proc.returncode != 0:
            problems.append(f"{task['id']}: solution.patch does not apply: "
                            f"{proc.stderr[-500:]}")
            return problems
        for i in range(repeats):
            ok, tail = grade_local(ws, task["test_cmd"], int(task.get("timeout", 120)))
            if not ok:
                problems.append(f"{task['id']}: reference fails "
                                f"(repeat {i + 1}/{repeats}). tail={tail[-500:]}")
                return problems
    return problems


def main() -> int:
    only = sys.argv[1:] or None
    tasks = list_tasks(only)
    assert tasks, "no tasks found"
    all_problems: list[str] = []
    for t in tasks:
        print(f"validating {t['id']} ({t['category']}/{t.get('difficulty')}) ...",
              flush=True)
        probs = check_task(t)
        all_problems.extend(probs)
        print(("  FAIL: " + "; ".join(probs)) if probs else "  ok", flush=True)
    print(f"\n{len(tasks) - len({p.split(':')[0] for p in all_problems})}/{len(tasks)} tasks valid")
    if all_problems:
        print("\n".join(all_problems))
        return 1
    # Fail-before/pass-after also calibrates difficulty: report the split plan.
    print("SPLIT: see evals/SPLIT.md (15 dev / 15 held-out).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
