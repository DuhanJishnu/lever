"""B6 verify loop: never trust "done" — run the tests.

When the model stops calling tools, the harness runs the project's own
visible tests (NEVER hidden grading tests) and feeds back a trimmed failure
report, up to VERIFY_MAX_ROUNDS rounds. No test files -> syntax-check all
.py files instead. Trace-based semantic checks (did the run itself invoke
tests? do files named in the answer exist?) ride along in the report.

Runs locally in the workspace (Docker grading stays in the eval runner).
All entry points are pure-ish and offline-testable; the loop owns events.
"""

from __future__ import annotations

import asyncio
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Cap on verify rounds per run: bounded cost, constant across configs.
VERIFY_MAX_ROUNDS = 3
VERIFY_TIMEOUT_S = 120
REPORT_TAIL_LINES = 40

SKIP_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache",
             "node_modules", "hidden_tests"}


@dataclass
class VerifyResult:
    passed: bool
    report: str
    command: list[str] = field(default_factory=list)
    ran_tests_in_trace: bool = False
    missing_files: list[str] = field(default_factory=list)


def _py_files(workspace: Path) -> list[Path]:
    return sorted(
        p for p in workspace.rglob("*.py")
        if p.is_file() and not any(d in p.parts for d in SKIP_DIRS)
    )


def has_tests(workspace: Path) -> bool:
    for p in _py_files(workspace):
        name = p.name
        if name.startswith("test_") or name.endswith("_test.py"):
            return True
        if p.parent.name == "tests":
            return True
    return False


def detect_test_cmd(workspace: Path) -> list[str] | None:
    """Visible-tests command, or None when there is nothing runnable."""
    if has_tests(workspace):
        return [sys.executable, "-m", "pytest", "-q"]
    if _py_files(workspace):
        return [sys.executable, "-m", "compileall", "-q", "."]
    return None


def trim_report(output: str) -> str:
    """First failing line + last REPORT_TAIL_LINES lines (model-sized)."""
    lines = output.splitlines()
    first_fail = next(
        (ln.strip() for ln in lines
         if re.search(r"^(FAILED|ERROR|E\s|assert|.*Error)", ln.strip())),
        "",
    )
    tail = "\n".join(lines[-REPORT_TAIL_LINES:])
    parts = []
    if first_fail:
        parts.append(f"First failure: {first_fail[:300]}")
    parts.append(f"Last {REPORT_TAIL_LINES} lines:\n{tail[-3000:]}")
    return "\n".join(parts)


async def run_tests(workspace: Path, timeout: int = VERIFY_TIMEOUT_S) -> tuple[
        bool, str, list[str]]:
    """Run visible tests. Returns (passed, trimmed_report, command)."""
    cmd = detect_test_cmd(workspace)
    if cmd is None:
        return True, "verify: no tests or python files found; nothing to check.", []
    # Fast edit->test loops can otherwise read stale bytecode when a rewrite
    # lands inside the same timestamp tick: verify current sources, always.
    for cache in workspace.rglob("__pycache__"):
        shutil.rmtree(cache, ignore_errors=True)
    shutil.rmtree(workspace / ".pytest_cache", ignore_errors=True)
    try:
        proc = await asyncio.to_thread(_run_sync, cmd, workspace, timeout)
    except subprocess.TimeoutExpired:
        return False, f"verify: `{_show(cmd)}` TIMED OUT after {timeout}s.", cmd
    tail = ((proc.stdout or "") + (proc.stderr or "")).strip()
    if proc.returncode != 0:
        return False, f"verify: `{_show(cmd)}` FAILED (exit {proc.returncode}).\n" + \
            trim_report(tail), cmd
    # compileall passes on dangling names (NameError is runtime, e.g. def
    # renamed but caller not updated). Catch bare calls to undefined names.
    dangling = undefined_calls(workspace)
    if dangling:
        shown = "\n".join(dangling[:10])
        return False, (f"verify: `{_show(cmd)}` passed syntax, but undefined "
                       f"name(s) would raise NameError at runtime:\n{shown}\n"
                       f"Update the call sites to the renamed function."), cmd
    return True, f"verify: `{_show(cmd)}` passed.\n{tail[-500:]}", cmd


def undefined_calls(workspace: Path) -> list[str]:
    """Bare `name(` calls with no matching def/import/builtin in that file.

    Same-file check only (cheap, no cross-file graph): catches the
    rename-without-caller bug (def sub_number + result = add_numbers).
    """
    import ast
    import builtins

    builtin_names = set(dir(builtins)) | {"__name__"}
    hits: list[str] = []
    for py in _py_files(workspace):
        try:
            tree = ast.parse(py.read_text(encoding="utf-8", errors="replace"),
                             filename=str(py))
        except (SyntaxError, ValueError):
            continue
        defined: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                defined.add(node.name)
                for a in list(node.args.args) + list(node.args.kwonlyargs):
                    defined.add(a.arg)
                if node.args.vararg:
                    defined.add(node.args.vararg.arg)
                if node.args.kwarg:
                    defined.add(node.args.kwarg.arg)
            elif isinstance(node, ast.ClassDef):
                defined.add(node.name)
            elif isinstance(node, ast.ImportFrom):
                for al in node.names:
                    defined.add(al.asname or al.name.split(".")[0])
            elif isinstance(node, ast.Import):
                for al in node.names:
                    defined.add((al.asname or al.name).split(".")[0])
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                defined.add(node.id)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                name = node.func.id
                if name not in defined and name not in builtin_names:
                    rel = py.name if py.parent == workspace else str(py.relative_to(workspace))
                    hits.append(f"{rel}:{node.lineno}: undefined `{name}()` "
                                f"(no def/import in this file)")
    return sorted(hits)


def _run_sync(cmd: list[str], cwd: Path, timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, check=False, cwd=cwd, capture_output=True,
                          text=True, timeout=timeout)


def _show(cmd: list[str]) -> str:
    return " ".join(cmd).replace(sys.executable, "python")


def trace_ran_tests(trace: Any) -> bool:
    """Did the agent itself invoke a test command? (hooks, not prose.)"""
    for it in trace or []:
        for ev in getattr(it, "tool_events", []) or []:
            if getattr(ev, "tool", "") == "bash":
                cmd = str((getattr(ev, "args", {}) or {}).get("cmd", ""))
                if "pytest" in cmd or "unittest" in cmd or "npm test" in cmd:
                    return True
    return False


def mentioned_files(answer: str) -> list[str]:
    return sorted(set(re.findall(r"[A-Za-z0-9_][A-Za-z0-9_/\.-]*\.py", answer or "")))


async def verify_completion(workspace: Path | str, answer: str,
                            trace: Any) -> VerifyResult:
    """Full B6 check: run visible tests + trace/file semantic checks."""
    ws = Path(workspace)
    passed, report, cmd = await run_tests(ws)
    missing = [f for f in mentioned_files(answer)
               if not (ws / f).exists() and not f.startswith(("http", "www."))]
    ran = trace_ran_tests(trace)
    extras = []
    if not ran:
        extras.append("Note: this run never invoked the test command itself.")
    if missing:
        extras.append(f"Note: answer names files not in workspace: "
                      f"{', '.join(missing[:5])}.")
    if extras:
        report = report + "\n" + "\n".join(extras)
    return VerifyResult(passed=passed, report=report, command=cmd,
                        ran_tests_in_trace=ran, missing_files=missing)
