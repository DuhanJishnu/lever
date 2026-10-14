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

# B2 head/tail budget (lines). Rationale: errors cluster at the head (usage,
# tracebacks start) and the tail (final result, failing assert); the middle
# of giant outputs is the most expendable context per token.
HEAD_LINES = 100
TAIL_LINES = 50


def cap_output(text: str) -> str:
    if len(text) <= MAX_OUTPUT_CHARS:
        return text
    return (
        text[:MAX_OUTPUT_CHARS]
        + f"\n[... output truncated at {MAX_OUTPUT_CHARS} chars (B0 coarse cap) ...]"
    )


def truncate_lines(text: str) -> str:
    """B2: keep head + tail with an explicit omission marker.

    Unlike cap_output (which amputates the tail), this preserves the ending —
    where exit codes, summaries, and failing asserts live.
    """
    lines = text.splitlines()
    if len(lines) <= HEAD_LINES + TAIL_LINES:
        return cap_output(text)  # short enough: char cap still applies
    omitted = len(lines) - HEAD_LINES - TAIL_LINES
    kept = (lines[:HEAD_LINES]
            + [f"[... {omitted} lines omitted (head/tail truncation) ...]"]
            + lines[-TAIL_LINES:])
    return cap_output("\n".join(kept))


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
    truncate: bool = False  # B2 output_truncation: head/tail instead of coarse cap

    @property
    def definitions(self) -> list[dict[str, Any]]:
        return [t.definition for t in self.by_name.values()]

    def _finish(self, text: str) -> str:
        return truncate_lines(text) if self.truncate else cap_output(text)

    async def run(self, name: str, args: dict[str, Any] | None) -> str:
        tool = self.by_name.get(name)
        if tool is None:
            known = ", ".join(sorted(self.by_name)) or "(none)"
            return self._finish(f'Unknown tool: "{name}". Available: {known}.')
        try:
            return self._finish(await tool.execute(args or {}))
        except Exception as e:  # model-friendly error, never a stack trace
            return self._finish(f"Error in {name}: {e}")
