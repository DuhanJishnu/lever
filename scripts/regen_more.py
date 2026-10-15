"""Regenerate solution.patch for x04/m05/m06 by transforming repo files.

Same lesson as scripts/regen_patches.py: never hand-write hunks. Here the
transforms are exact string replacements on the real files, so counts and
context are correct by construction.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from regen_patches import git_patch

TASKS = Path("evals/tasks")


def build(task: str, transforms: dict[str, str | None]) -> None:
    repo = TASKS / task / "repo"
    chunks = []
    for rel in sorted(
        {str(p.relative_to(repo)).replace("\\", "/")
         for p in repo.rglob("*") if p.is_file()} | set(transforms)
    ):
        old_p = repo / rel
        old = old_p.read_text(encoding="utf-8") if old_p.exists() else None
        spec = transforms.get(rel, "SAME")
        if spec == "SAME":
            continue
        new = spec  # full fixed content (may be None = delete)
        if old != new:
            chunks.append(git_patch(old, new, rel))
    out = TASKS / task / "solution.patch"
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write("".join(chunks))
    print(f"{task}: rewrote solution.patch ({len(chunks)} chunks)")


def main() -> None:
    x04 = (TASKS / "x04" / "repo" / "rates.py").read_text(encoding="utf-8")
    assert "return RATES.get(code, 0.0)" in x04
    build("x04", {"rates.py": x04.replace(
        "return RATES.get(code, 0.0)", "return RATES.get(code.lower(), 0.0)", 1)})

    m05 = (TASKS / "m05" / "repo" / "store.py").read_text(encoding="utf-8")
    assert "for r in rows[:-1]:" in m05
    build("m05", {"store.py": m05.replace(
        "for r in rows[:-1]:", "for r in rows:", 1)})

    billing = (TASKS / "m06" / "repo" / "billing.py").read_text(encoding="utf-8")
    fixed_billing = billing.replace(
        "def invoice(lines):", "from money import fmt\n\n\ndef invoice(lines):", 1)
    fixed_billing = fixed_billing.replace(
        'return f"{inv[\'lines\']} lines, total {inv[\'total\']:.2f}"',
        'return f"{inv[\'lines\']} lines, total {fmt(inv[\'total\'])}"', 1)
    assert fixed_billing != billing
    report = (TASKS / "m06" / "repo" / "report.py").read_text(encoding="utf-8")
    fixed_report = report.replace(
        "from billing import invoice, render",
        "from money import fmt\n\nfrom billing import invoice, render", 1)
    assert fixed_report != report
    build("m06", {
        "billing.py": fixed_billing,
        "money.py": 'def fmt(cents):\n    return f"${cents / 100:.2f}"\n',
        "report.py": fixed_report,
    })


if __name__ == "__main__":
    main()
