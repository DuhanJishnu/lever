"""bash tool — run a shell command with the workspace as cwd.

B0 is deliberately permissive (no allowlist — that arrives with the policy
layer in Phase 4). Safety here = timeout + workspace cwd + output cap.
Docker isolation arrives in Phase 2; until then this runs locally.
"""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path
from typing import Any

from .base import Tool


def make_bash_tool(root: Path) -> Tool:
    async def _run(args: dict[str, Any]) -> str:
        cmd = str(args.get("cmd", ""))
        timeout = int(args.get("timeout", 30))
        if not cmd.strip():
            return "bash: empty command."

        def _exec() -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                cmd,
                shell=True,
                check=False,
                cwd=root,
                capture_output=True,
                text=True,
                timeout=timeout,
            )

        try:
            proc = await asyncio.to_thread(_exec)
        except subprocess.TimeoutExpired:
            return f"bash: timed out after {timeout}s: {cmd!r}."
        merged = (proc.stdout or "") + (proc.stderr or "")
        return f"$ {cmd}\nexit={proc.returncode}\n{merged.strip()}"

    return Tool(
        name="bash",
        description="Run a shell command with the workspace as working directory. Returns exit code + output. Has a timeout (default 30s).",
        parameters={
            "type": "object",
            "properties": {
                "cmd": {"type": "string"},
                "timeout": {"type": "integer"},
            },
            "required": ["cmd"],
        },
        execute=_run,
    )
