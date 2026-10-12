"""read_file / write_file tools, bound to a session workspace."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import Tool, resolve_safe


def make_read_tool(root: Path) -> Tool:
    async def _run(args: dict[str, Any]) -> str:
        path = resolve_safe(root, str(args.get("path", "")))
        if not path.is_file():
            return f"read_file: no such file: {args.get('path')!r}. Use grep to find the right path."
        return path.read_text(encoding="utf-8", errors="replace")

    return Tool(
        name="read_file",
        description="Read a file's full content. Path is relative to the workspace root.",
        parameters={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
        execute=_run,
    )


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
