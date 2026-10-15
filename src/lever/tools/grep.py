"""grep tool — regex search across the workspace."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .base import Tool

SKIP_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", "node_modules", ".ruff_cache"}
MAX_FILE_BYTES = 1_000_000
MAX_MATCHES = 50


def make_grep_tool(root: Path) -> Tool:
    # Absolute once: rglob results are absolute, and relative_to() below
    # needs a matching base (relative root + absolute file = ValueError).
    root = root.resolve()

    async def _run(args: dict[str, Any]) -> str:
        import warnings

        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", FutureWarning)
                rx = re.compile(str(args.get("pattern", "")))
        except re.error as e:
            return f"grep: invalid regex {args.get('pattern')!r}: {e}"
        sub = str(args.get("path", "."))
        base = (root / sub).resolve()
        if not base.exists():
            return f"grep: no such path: {sub!r}."
        files: list[Path] = []
        if base.is_file():
            files = [base]
        else:
            for p in sorted(base.rglob("*")):
                if (
                    p.is_file()
                    and not any(d in p.parts for d in SKIP_DIRS)
                    and p.stat().st_size <= MAX_FILE_BYTES
                ):
                    files.append(p)
        out: list[str] = []
        for f in files:
            try:
                raw = f.read_bytes()
                if b"\x00" in raw[:4096]:
                    continue  # binary
                text = raw.decode("utf-8", errors="replace")
            except OSError:
                continue
            for i, line in enumerate(text.splitlines(), 1):
                if rx.search(line):
                    rel = f.relative_to(root)
                    out.append(f"{rel}:{i}: {line.strip()[:200]}")
                    if len(out) >= MAX_MATCHES:
                        out.append(f"[... capped at {MAX_MATCHES} matches ...]")
                        return "\n".join(out)
        return "\n".join(out) if out else "No matches."

    return Tool(
        name="grep",
        description="Regex-search file contents. Returns file:line matches (max 50). Path defaults to workspace root.",
        parameters={
            "type": "object",
            "properties": {
                "pattern": {"type": "string"},
                "path": {"type": "string"},
            },
            "required": ["pattern"],
        },
        execute=_run,
    )
