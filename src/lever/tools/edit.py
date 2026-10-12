"""edit_file tool — B0 version: EXACT match only. Tolerance arrives in B1."""

from __future__ import annotations

import difflib
from pathlib import Path
from typing import Any

from .base import Tool, resolve_safe


def make_edit_tool(root: Path) -> Tool:
    async def _run(args: dict[str, Any]) -> str:
        path = resolve_safe(root, str(args.get("path", "")))
        old = str(args.get("old_str", ""))
        new = str(args.get("new_str", ""))
        if not path.is_file():
            return f"edit_file: no such file: {args.get('path')!r}."
        if not old:
            return "edit_file: old_str is empty. Provide the exact block to replace."
        content = path.read_text(encoding="utf-8", errors="replace")
        hits = content.count(old)
        if hits == 0:
            return (
                "edit_file: old_str not found (exact match required in B0). "
                "Re-read the file and copy the block exactly, including whitespace."
            )
        if hits > 1:
            return (
                f"edit_file: old_str matches {hits} locations. "
                "Add more surrounding context to make it unique, or use replace_all."
            )
        updated = content.replace(old, new, 1)
        path.write_text(updated, encoding="utf-8")
        diff = "".join(
            difflib.unified_diff(
                content.splitlines(True),
                updated.splitlines(True),
                fromfile=f"a/{args.get('path')}",
                tofile=f"b/{args.get('path')}",
            )
        )
        return f"Edit applied.\n{diff}" if diff else "Edit applied (no visible change)."

    return Tool(
        name="edit_file",
        description="Replace one exact block of text in a file (old_str must match exactly once). Returns a unified diff.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "old_str": {"type": "string"},
                "new_str": {"type": "string"},
            },
            "required": ["path", "old_str", "new_str"],
        },
        execute=_run,
    )
