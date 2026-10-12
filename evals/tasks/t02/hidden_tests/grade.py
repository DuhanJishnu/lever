"""Hidden grader for write-tests tasks: agent-written tests must exist, pass, and be numerous."""

import re
import subprocess
import sys
from pathlib import Path

MIN_TESTS = 6

root = Path(__file__).resolve().parent.parent
files = sorted((root / "tests").glob("test_*.py"))
assert files, "GRADE FAIL: no tests/test_*.py found (write tests under tests/)."
count = sum(len(re.findall(r"^\s*def test_", p.read_text(encoding="utf-8"), re.M))
            for p in files)
assert count >= MIN_TESTS, f"GRADE FAIL: only {count} tests, need >= {MIN_TESTS}."
proc = subprocess.run([sys.executable, "-m", "pytest", "tests", "-q"],
                      check=False, cwd=root,
                      capture_output=True, text=True, timeout=120)
print(proc.stdout[-1500:])
assert proc.returncode == 0, "GRADE FAIL: agent-written tests do not all pass."
print(f"GRADE PASS: {count} tests, all green.")
