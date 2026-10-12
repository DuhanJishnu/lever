"""Tool primitives: safe paths, output cap, Tool + ToolRegistry types.

Canonical tool definition form (provider-agnostic):
    {"name": ..., "description": ..., "parameters": {...JSON schema...}}
Providers translate this to SDK-specific shapes (see GeminiProvider._to_tools).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# B0 coarse output cap — deliberately naive. Documented as part of the baseline:
# every config (B0..B8) caps tool output; B2 only makes the cap smarter (head/tail).
MAX_OUTPUT_CHARS = 20_000


def cap_output(text: str) -> str:
    if len(text) <= MAX_OUTPUT_CHARS:
        return text
    return (
        text[:MAX_OUTPUT_CHARS]
        + f"\n[... output truncated at {MAX_OUTPUT_CHARS} chars (B0 coarse cap) ...]"
    )


def resolve_safe(root: Path, user_path: str) -> Path:
    """Resolve a tool-supplied path inside the workspace. Reject `..` escapes."""
    root = root.resolve()
    p = (root / user_path).resolve()
    if not p.is_relative_to(root):
        raise ValueError(
            f"Path escapes workspace: {user_path!r}. "
            f"All paths must stay inside {root}."
        )
    return p


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    execute: Callable[[dict[str, Any]], Awaitable[str]]

    @property
    def definition(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }


@dataclass
class ToolRegistry:
    by_name: dict[str, Tool] = field(default_factory=dict)

    @property
    def definitions(self) -> list[dict[str, Any]]:
        return [t.definition for t in self.by_name.values()]

    async def run(self, name: str, args: dict[str, Any] | None) -> str:
        tool = self.by_name.get(name)
        if tool is None:
            known = ", ".join(sorted(self.by_name)) or "(none)"
            return cap_output(f'Unknown tool: "{name}". Available: {known}.')
        try:
            return cap_output(await tool.execute(args or {}))
        except Exception as e:  # model-friendly error, never a stack trace
            return cap_output(f"Error in {name}: {e}")
