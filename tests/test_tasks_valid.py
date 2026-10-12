import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, "src")
sys.path.insert(0, "evals")

from runner import list_tasks


def test_task_inventory_and_split():
    tasks = list_tasks()
    assert len(tasks) == 30, f"expected 30 tasks, got {len(tasks)}"
    counts = Counter(t["category"] for t in tasks)
    assert counts == {
        "bugfix": 10, "feature": 8, "refactor": 5,
        "multi-file": 4, "write-tests": 3,
    }, dict(counts)
    split = (Path("evals/SPLIT.md")).read_text(encoding="utf-8")
    ids = {t["id"] for t in tasks}
    for tid in ids:
        assert tid in split, f"{tid} missing from SPLIT.md"
    traps = [t["id"] for t in tasks if t.get("trap")]
    assert len(traps) >= 6, f"want >=6 trap tasks, got {len(traps)}"


def test_reference_solutions_validate():
    """Full gate: every task FAILS pre-patch and PASSES 3x post-patch."""
    sys.path.insert(0, "evals")
    from runner import list_tasks as lt
    from validate_tasks import check_task

    problems: list[str] = []
    for t in lt():
        problems.extend(check_task(t))
    assert not problems, "\n".join(problems)
