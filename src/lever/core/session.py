"""Session: workspace lifecycle + identity.

B0 workspace strategy: COPY the source repo into `.lever_workspaces/<session_id>/`
(excluding VCS/venv noise) and `git init` a baseline commit there. This gives
clean `git diff`s for the UI without git-worktree quirks on Windows. Docker +
true worktrees can replace this later without changing the interface, because
tools only ever see `session.workspace`.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .events import new_session_id

IGNORE = shutil.ignore_patterns(
    ".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache",
    "node_modules", ".lever_events.db*",
)


@dataclass
class Session:
    source: Path
    session_id: str = field(default_factory=new_session_id)
    workspace: Path | None = None

    def open(self, base_dir: Path | str = ".lever_workspaces") -> Path:
        ws = Path(base_dir) / self.session_id
        if ws.exists():
            shutil.rmtree(ws)
        shutil.copytree(self.source, ws, ignore=IGNORE)
        self.workspace = ws
        self._git_baseline(ws)
        return ws

    def close(self) -> None:
        # B0: workspace persists for inspection (diffs, debugging).
        # Later phases may add cleanup policies here. Method exists so the
        # harness lifecycle (try/finally close) is honored from day one.
        return None

    def get_diff(self) -> str:
        if self.workspace is None:
            return ""
        try:
            out = subprocess.run(
                ["git", "diff", "--stat"],
                check=False,
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=15,
            )
            return out.stdout.strip()
        except OSError:
            return ""

    @staticmethod
    def _git_baseline(ws: Path) -> None:
        try:
            subprocess.run(["git", "init", "-q"], cwd=ws, check=True,
                           capture_output=True, timeout=30)
            subprocess.run(["git", "add", "-A"], cwd=ws, check=True,
                           capture_output=True, timeout=30)
            subprocess.run(
                ["git", "-c", "user.email=lever@local",
                 "-c", "user.name=lever", "commit", "-qm", "baseline"],
                cwd=ws, check=True, capture_output=True, timeout=30,
            )
        except (OSError, subprocess.SubprocessError):
            pass  # baseline commit is convenience, not required
