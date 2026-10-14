"""Session-bound tool factory (dependency injection).

Tools are created PER SESSION from that session's workspace handle — they never
import environment state directly. This enables parallel eval runs, unit tests
against a temp dir, and clean lifecycle management.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import ToolRegistry
from .bash import make_bash_tool
from .edit import make_edit_tool
from .fs import make_read_tool, make_write_tool
from .grep import make_grep_tool
from .todo import make_todo_tool


def create_tools(workspace: Path | str, config: Any | None = None) -> ToolRegistry:
    root = Path(workspace)
    tolerant = bool(getattr(config, "tolerant_edit", False))
    trunc = bool(getattr(config, "output_truncation", False))
    tools = [
        make_read_tool(root, ranged=trunc),
        make_write_tool(root),
        make_edit_tool(root, tolerant=tolerant),
        make_grep_tool(root),
        make_bash_tool(root),
    ]
    if bool(getattr(config, "planner_prompt", False)):
        tools.append(make_todo_tool())  # scratchpad only with the planner prompt
    return ToolRegistry(by_name={t.name: t for t in tools}, truncate=trunc)
