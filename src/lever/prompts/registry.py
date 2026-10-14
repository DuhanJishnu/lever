"""Versioned system prompts (B7 prompt registry).

prompts/vN/*.md split the system prompt into reviewable sections; the loop
renders one version per run, so prompt A/B is a config diff, not a code fork.
`{tools}` placeholders render the registered tool names, keeping prompt and
tool surface consistent by construction. v1 = naive baseline shape; v2 =
planner workflow + scratchpad + few-shot examples.
"""

from __future__ import annotations

from pathlib import Path

SECTIONS = ("role", "workflow", "tools", "edits", "done", "examples")


def available_versions() -> list[str]:
    base = Path(__file__).parent
    return sorted(p.name for p in base.iterdir()
                  if p.is_dir() and (p / "role.md").exists())


def render_system(version: str, tool_names: list[str]) -> str:
    """Render version's sections joined; unknown version falls back to v1."""
    base = Path(__file__).parent / version
    if not (base / "role.md").exists():
        base = Path(__file__).parent / "v1"
    tools = ", ".join(tool_names)
    parts = []
    for section in SECTIONS:
        path = base / f"{section}.md"
        if path.exists():
            parts.append(path.read_text(encoding="utf-8").strip()
                         .replace("{tools}", tools))
    return "\n\n".join(p for p in parts if p)
