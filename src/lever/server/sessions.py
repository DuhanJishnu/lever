"""Server-side session registry: workspaces, configs, background runs, approvals.

One SQLite event store holds every session (session_id column multiplexes).
Each record owns: workspace Session, effective HarnessConfig, provider kind,
asyncio run task, and pending approval futures keyed by request id.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Any

from ..core.session import Session


@dataclass
class SessionRecord:
    id: str
    source: str
    task: str | None = None
    config: dict[str, Any] = field(default_factory=dict)
    provider: str = "auto"
    status: str = "idle"  # idle | running | waiting_approval | done | error
    session: Session | None = None
    run_task: asyncio.Task[Any] | None = None
    pending: dict[str, asyncio.Future[Any]] = field(default_factory=dict)
    error: str = ""


def new_id() -> str:
    return uuid.uuid4().hex[:12]


class Registry:
    def __init__(self) -> None:
        self.sessions: dict[str, SessionRecord] = {}

    def create(self, source: str, task: str | None = None,
               config: dict[str, Any] | None = None,
               provider: str = "auto") -> SessionRecord:
        rec = SessionRecord(id=new_id(), source=source, task=task,
                            config=config or {}, provider=provider)
        self.sessions[rec.id] = rec
        return rec

    def get(self, sid: str) -> SessionRecord | None:
        return self.sessions.get(sid)

    def list(self) -> list[SessionRecord]:
        return list(self.sessions.values())
