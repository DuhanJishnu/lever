"""todo scratchpad tool (B7): the model's plan, owned by the harness.

State lives in the registry closure (per session), NOT in messages — so it
survives compaction by construction (stronger than "pinned tier" placement).
Calls/results are event-logged like any tool, so replay shows the plan.
"""

from __future__ import annotations

from typing import Any

from .base import Tool


def make_todo_tool() -> Tool:
    items: list[dict[str, Any]] = []

    def _render() -> str:
        if not items:
            return "todo: empty. Add plan steps first."
        lines = []
        for i, it in enumerate(items, 1):
            mark = "x" if it["done"] else " "
            lines.append(f"{i}. [{mark}] {it['item']}")
        return "todo:\n" + "\n".join(lines)

    async def _run(args: dict[str, Any]) -> str:
        action = str(args.get("action", "list")).lower()
        if action == "add":
            item = str(args.get("item", "")).strip()
            if not item:
                return "todo add needs an `item` string."
            items.append({"item": item, "done": False})
            return _render()
        if action == "done":
            try:
                idx = int(args.get("index", 0)) - 1
            except (TypeError, ValueError):
                return "todo done needs a 1-based `index`."
            if 0 <= idx < len(items):
                items[idx]["done"] = True
                return _render()
            return f"todo done: index out of range (1-{len(items)})."
        if action == "clear":
            items.clear()
            return "todo: cleared."
        if action == "list":
            return _render()
        return (f"todo: unknown action {action!r}. "
                f"Use add/list/done/clear.")

    return Tool(
        name="todo",
        description=("Scratchpad for your plan: add steps before editing, "
                     "list to review, done with the step number when finished."),
        parameters={
            "type": "object",
            "properties": {
                "action": {"type": "string"},
                "item": {"type": "string"},
                "index": {"type": "integer"},
            },
            "required": ["action"],
        },
        execute=_run,
    )
