"""One-off repair: regenerate solution.patch files from embedded reference contents.

Lesson learned: hand-written unified-diff hunk headers with wrong line counts
make `git apply` succeed yet silently truncate files. Generating diffs with
difflib is correct by construction. (Kept as a script for the video autopsy.)
"""

from __future__ import annotations

import difflib
from pathlib import Path

TASKS = Path("evals/tasks")

# task -> {relpath: fixed content, or None to delete the file}
FIXED: dict[str, dict[str, str | None]] = {
    "f01": {"clamp.py": "def clamp(x, lo, hi):\n    if x < lo:\n        return lo\n    if x > hi:\n        return hi\n    return x\n"},
    "f05": {"dedup.py": "def dedup(lst):\n    seen = set()\n    out = []\n    for x in lst:\n        if x not in seen:\n            seen.add(x)\n            out.append(x)\n    return out\n"},
    "m01": {
        "a.py": "from util import helper\n\n\ndef run(x):\n    return helper(x) + 1\n",
        "b.py": "from util import helper\n\n\ndef run2(x):\n    return helper(x) - 1\n",
        "util.py": "def helper(x):\n    return x * 2\n",
    },
    "m02": {
        "alpha.py": "def new_name(x):\n    return x + 1\n\n\ndef caller(x):\n    return new_name(x) * 10\n",
        "beta.py": "from alpha import new_name\n\n\ndef shifted(x):\n    return new_name(x) - 1\n",
    },
    "m04": {
        "add.py": "def add(a, b):\n    return a + b\n",
        "mul.py": "def mul(a, b):\n    return a * b\n",
        "ops.py": None,
        "user.py": "from add import add\nfrom mul import mul\n\n\ndef poly(x):\n    return add(mul(x, x), mul(2, x))\n",
    },
    "r01": {"totals.py": "def sum_if(nums, pred):\n    total = 0\n    for n in nums:\n        if pred(n):\n            total += n\n    return total\n\n\ndef sum_even(nums):\n    return sum_if(nums, lambda n: n % 2 == 0)\n\n\ndef sum_odd(nums):\n    return sum_if(nums, lambda n: n % 2 != 0)\n"},
    "r03": {"users.py": "def active_users(users):\n    return [u for u in users if u.get(\"active\")]\n\n\ndef format_names(users):\n    return [u[\"name\"].strip().title() for u in users]\n\n\ndef process(users):\n    return format_names(active_users(users))\n"},
    "r04": {"point.py": "from dataclasses import dataclass\n\n\n@dataclass\nclass Point:\n    x: float\n    y: float\n"},
    "t01": {"tests/test_strutil.py": "from strutil import repeat, shout, whisper\n\n\ndef test_shout():\n    assert shout(\"hi\") == \"HI!\"\n\n\ndef test_shout_empty():\n    assert shout(\"\") == \"!\"\n\n\ndef test_whisper():\n    assert whisper(\"  HeLLo \") == \"hello\"\n\n\ndef test_repeat():\n    assert repeat(\"ab\", 3) == \"ababab\"\n\n\ndef test_repeat_zero():\n    assert repeat(\"ab\", 0) == \"\"\n"},
    "t02": {"tests/test_mathx.py": "from mathx import gcd, is_prime, lcm\n\n\ndef test_gcd():\n    assert gcd(12, 8) == 4\n\n\ndef test_gcd_zero():\n    assert gcd(0, 5) == 5\n\n\ndef test_lcm():\n    assert lcm(4, 6) == 12\n\n\ndef test_lcm_zero():\n    assert lcm(0, 7) == 0\n\n\ndef test_primes():\n    assert is_prime(13) is True\n    assert is_prime(15) is False\n\n\ndef test_prime_edges():\n    assert is_prime(2) is True\n    assert is_prime(1) is False\n    assert is_prime(0) is False\n"},
}


def git_patch(old: str | None, new: str | None, path: str) -> str:
    if old is not None and not old.endswith("\n"):
        old += "\n"
    if new is not None and not new.endswith("\n"):
        new += "\n"
    if old is None:  # new file
        head = (f"diff --git a/{path} b/{path}\nnew file mode 100644\n"
                f"--- /dev/null\n+++ b/{path}\n")
        body = "".join(difflib.unified_diff([], new.splitlines(True),
                                            "/dev/null", f"b/{path}",
                                            n=3))
        return head + "\n".join(body.splitlines()[2:]) + "\n"
    if new is None:  # deletion
        head = (f"diff --git a/{path} b/{path}\ndeleted file mode 100644\n"
                f"--- a/{path}\n+++ /dev/null\n")
        body = "".join(difflib.unified_diff(old.splitlines(True), [],
                                            f"a/{path}", "/dev/null",
                                            n=3))
        return head + "\n".join(body.splitlines()[2:]) + "\n"
    head = f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n"
    body = "".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
                                        f"a/{path}", f"b/{path}",
                                        n=3))
    return head + "\n".join(body.splitlines()[2:]) + "\n"


def main() -> None:
    for tid, files in FIXED.items():
        repo = TASKS / tid / "repo"
        chunks = []
        for rel in sorted(set(files) | {str(p.relative_to(repo)).replace("\\", "/")
                                        for p in repo.rglob("*") if p.is_file()}):
            old_p = repo / rel
            old = old_p.read_text(encoding="utf-8") if old_p.exists() else None
            new = files.get(rel, old)  # unlisted files: unchanged (no chunk)
            if rel in files and new != old:
                chunks.append(git_patch(old, new, rel))
        with open(TASKS / tid / "solution.patch", "w", encoding="utf-8",
                   newline="\n") as f:
            f.write("".join(chunks))
        print(f"{tid}: rewrote solution.patch ({len(chunks)} file chunks)")


if __name__ == "__main__":
    main()
