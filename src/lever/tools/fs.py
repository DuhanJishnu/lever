"""read_file / write_file tools, bound to a session workspace."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import Tool, resolve_safe

# B2 default read window: first chunk of a big file + pointer to the rest.
READ_DEFAULT_LINES = 100


def make_read_tool(root: Path, ranged: bool = False) -> Tool:
    async def _run(args: dict[str, Any]) -> str:
        path = resolve_safe(root, str(args.get("path", "")))
        if not path.is_file():
            return f"read_file: no such file: {args.get('path')!r}. Use grep to find the right path."
        text = path.read_text(encoding="utf-8", errors="replace")
        if not ranged:
            return text
        lines = text.splitlines()
        total = len(lines)
        start = _to_index(args.get("start_line"), 1, total)
        default_end = min(READ_DEFAULT_LINES, total) if total else 1
        end = _to_index(args.get("end_line"), default_end, total)
        if start > end:
            return (f"read_file: empty range (start_line={start} > end_line={end}; "
                    f"file has {total} lines).")
        chunk = "\n".join(lines[start - 1:end])
        head = f"[{args.get('path')}: lines {start}-{end} of {total}]\n"
        if start == 1 and end == total:
            return text  # small file: whole thing, no wrapper
        if end < total:
            chunk += (f"\n[... {total - end} more lines: re-read with "
                      f"start_line={end + 1} ...]")
        return head + chunk

    desc = "Read a file's content. Path is relative to the workspace root."
    props: dict[str, Any] = {"path": {"type": "string"}}
    if ranged:
        desc += (f" By default returns the first {READ_DEFAULT_LINES} lines; "
                 "use start_line/end_line (1-based, inclusive) for the rest.")
        props["start_line"] = {"type": "integer"}
        props["end_line"] = {"type": "integer"}
    return Tool(
        name="read_file",
        description=desc,
        parameters={
            "type": "object",
            "properties": props,
            "required": ["path"],
        },
        execute=_run,
    )


def _to_index(value: Any, default: int, total: int) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default if total == 0 else min(default, total)
    if total == 0:
        return 1
    return max(1, min(n, total))


def make_write_tool(root: Path) -> Tool:
    async def _run(args: dict[str, Any]) -> str:
        path = resolve_safe(root, str(args.get("path", "")))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(args.get("content", "")), encoding="utf-8")
        return f"Wrote {len(str(args.get('content', '')))} chars to {args.get('path')}."

    return Tool(
        name="write_file",
        description="Create or overwrite a file. Parent directories are created. Path is relative to the workspace root.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        },
        execute=_run,
    )
