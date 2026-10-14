"""Core event model — immutable, JSON-serializable, event-sourced session log."""

from __future__ import annotations

import time
import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field

EventType = Literal[
    "user_message",
    "model_request",
    "model_response",
    "tool_call",
    "tool_result",
    "approval_request",
    "approval_decision",
    "context_compacted",
    "policy_block",
    "checkpoint",
    "error",
    "session_end",
    "harness_nudge",
]


class Event(BaseModel):
    id: int | None = None
    session_id: str
    seq: int
    ts: float = Field(default_factory=time.time)
    type: EventType
    data: dict[str, Any]


def new_session_id() -> str:
    return uuid.uuid4().hex[:12]
