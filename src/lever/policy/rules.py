"""Shipped policy rules (Phase 4.1 spec).

- ConfineRule: deny any file-tool path escaping the workspace (defense in
  depth alongside resolve_safe; uniform event trail).
- BashAllowlistRule: allow listed binaries, ask for anything else.
- TokenBudgetRule: ask once cumulative model tokens pass the budget.
- InstallThenPushRule: after pip/npm/uv install, ask before git push or
  network access (curl/wget/further installs). History-scanned, stateless.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .engine import Decision, ProposedCall

PATH_TOOLS = ("read_file", "write_file", "edit_file", "grep")

DEFAULT_BASH_ALLOWLIST = frozenset({
    "python", "pytest", "ls", "dir", "cat", "type", "echo", "git",
    "ruff", "find", "pwd", "whoami", "ver", "set", "node",
})

INSTALL_RE = re.compile(r"\b(pip|npm|uv)\s+install\b")
PUSH_RE = re.compile(r"\bgit\b.*\bpush\b")
NETWORK_RE = re.compile(r"\b(curl|wget)\b|pip\s+download")


@dataclass
class ConfineRule:
    root: Path | str

    def evaluate(self, history: list[Any], call: ProposedCall) -> Decision:
        if call.tool not in PATH_TOOLS:
            return Decision.allow()
        raw = str((call.args or {}).get("path", ""))
        if not raw:
            return Decision.allow()
        root = Path(self.root).resolve()
        try:
            target = (root / raw).resolve()
        except (OSError, ValueError) as e:
            return Decision.deny(f"unresolvable path {raw!r}: {e}")
        if not target.is_relative_to(root):
            return Decision.deny(f"path escapes workspace: {raw!r}")
        return Decision.allow()


@dataclass
class BashAllowlistRule:
    allow: frozenset[str] = field(default_factory=lambda: DEFAULT_BASH_ALLOWLIST)

    @staticmethod
    def _binary(cmd: str) -> str:
        try:
            first = shlex.split(cmd, posix=False)[0]
        except (ValueError, IndexError):
            return ""
        base = first.strip('"').split("/")[-1].split("\\")[-1].lower()
        return base.removesuffix(".exe")

    def evaluate(self, history: list[Any], call: ProposedCall) -> Decision:
        if call.tool != "bash":
            return Decision.allow()
        binary = self._binary(str((call.args or {}).get("cmd", "")))
        if not binary:
            return Decision.deny("empty bash command")
        if binary in self.allow:
            return Decision.allow()
        return Decision.ask(f"bash binary {binary!r} is outside the allowlist")


@dataclass
class TokenBudgetRule:
    budget_tokens: int | None = None

    def evaluate(self, history: list[Any], call: ProposedCall) -> Decision:
        if self.budget_tokens is None:
            return Decision.allow()
        total = 0
        for e in history:
            if getattr(e, "type", "") == "model_response":
                data = getattr(e, "data", {}) or {}
                total += int(data.get("input_tokens", 0) or 0)
                total += int(data.get("output_tokens", 0) or 0)
        if total >= self.budget_tokens:
            return Decision.ask(
                f"token budget exceeded ({total} >= {self.budget_tokens})")
        return Decision.allow()


@dataclass
class InstallThenPushRule:
    def _installed(self, history: list[Any]) -> bool:
        for e in history:
            if getattr(e, "type", "") != "tool_call":
                continue
            data = getattr(e, "data", {}) or {}
            if data.get("name") != "bash":
                continue
            if INSTALL_RE.search(str((data.get("args", {}) or {}).get("cmd", ""))):
                return True
        return False

    def evaluate(self, history: list[Any], call: ProposedCall) -> Decision:
        if call.tool != "bash" or not self._installed(history):
            return Decision.allow()
        cmd = str((call.args or {}).get("cmd", ""))
        if PUSH_RE.search(cmd):
            return Decision.ask("git push after package install needs approval")
        if NETWORK_RE.search(cmd):
            return Decision.ask("network access after package install needs approval")
        return Decision.allow()
