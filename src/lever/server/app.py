"""Lever HTTP server: sessions, live event streams, human approvals.

Single-task sessions (the loop runs one task per session): create a session,
start it with a message, watch events over SSE, approve/deny tool calls when
the policy asks, fork history prefixes for retries. Forking copies the event
prefix into a fresh session + workspace (fork-for-retry, not mid-run resume —
documented limitation, matches the loop's single-task shape).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from ..core.config import HarnessConfig
from ..core.events import Event
from ..store.sqlite import EventStore
from .sessions import Registry, SessionRecord

APPROVAL_TIMEOUT_S = 600.0
STREAM_POLL_S = 0.5
STREAM_TIMEOUT_S = 3600.0


class CreateBody(BaseModel):
    repo: str
    task: str | None = None
    config: dict[str, Any] = {}
    provider: str = "auto"
    token_budget: int | None = None


class MessageBody(BaseModel):
    content: str


class ApprovalBody(BaseModel):
    allow: bool = True


def _read_summaries(root: str) -> dict[str, Any]:
    import glob
    import json as _json

    out: dict[str, Any] = {}
    pattern = str(Path(root) / "evals" / "results" / "*_summary.json")
    for path in sorted(glob.glob(pattern)):
        try:
            with open(path, encoding="utf-8") as f:
                out[Path(path).stem] = _json.load(f)
        except (OSError, ValueError):
            continue
    return out


def _provider(kind: str, custom: dict[str, Any] | None = None) -> tuple[Any, str]:
    if custom and kind in custom:
        factory: Any = custom[kind]
        made: tuple[Any, str] = factory()
        return made
    if kind == "fake":
        from ..providers.fake import FakeProvider

        return FakeProvider.say_hi(), "fake"
    if kind == "local":
        from ..providers.local import LocalProvider

        local: Any = LocalProvider()
        return local, f"local:{local.model}"
    if kind == "gemini":
        from ..providers.gemini import GeminiProvider

        gemini: Any = GeminiProvider()
        return gemini, str(gemini.model)
    # auto: gemini when keyed, else fake (never spends by accident)
    import os

    if os.getenv("GEMINI_API_KEY"):
        from ..providers.gemini import GeminiProvider

        auto: Any = GeminiProvider()
        return auto, str(auto.model)
    from ..providers.fake import FakeProvider

    return FakeProvider.say_hi(), "fake"


def _config(overrides: dict[str, Any]) -> HarnessConfig:
    base = HarnessConfig.b0()
    if overrides:
        base = base.model_copy(update=overrides)
    return base


def _policy(workspace: Path, token_budget: int | None) -> Any:
    from ..policy.engine import PolicyEngine
    from ..policy.rules import (
        BashAllowlistRule,
        ConfineRule,
        InstallThenPushRule,
        TokenBudgetRule,
    )

    return PolicyEngine([
        ConfineRule(workspace),
        InstallThenPushRule(),
        BashAllowlistRule(),
        TokenBudgetRule(token_budget),
    ])


def create_app(db_path: str = ".lever_sessions.db",
               providers: dict[str, Any] | None = None,
               root: str | Path = ".") -> FastAPI:
    app = FastAPI(title="Lever")
    app.add_middleware(
        CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
        allow_headers=["*"])
    app.state.registry = Registry()
    app.state.store = EventStore(db_path)
    app.state.db_path = db_path
    app.state.root = str(root)
    app.state.providers = dict(providers or {})

    def store() -> EventStore:
        state_store: EventStore = app.state.store
        return state_store

    def reg() -> Registry:
        state_reg: Registry = app.state.registry
        return state_reg

    async def _run_session(rec: SessionRecord, task_text: str) -> None:
        from ..core.loop import run_loop
        from ..core.session import Session

        rec.status = "running"
        rec.task = task_text
        try:
            if rec.session is None:
                rec.session = Session(source=Path(rec.source))
                # The workspace session must log under the API session id —
                # otherwise events and registry diverge (two ids, lost log).
                rec.session.session_id = rec.id
                rec.session.open()
            assert rec.session.workspace is not None
            provider, _name = _provider(rec.provider, app.state.providers)
            cfg = _config(rec.config)
            policy = _policy(rec.session.workspace,
                             rec.config.get("token_budget"))
            loop = asyncio.get_running_loop()

            async def approve(request: dict[str, Any]) -> bool:
                req_id = str(request.get("req_id", ""))
                fut = loop.create_future()
                rec.pending[req_id] = fut
                rec.status = "waiting_approval"
                try:
                    return bool(await asyncio.wait_for(
                        fut, APPROVAL_TIMEOUT_S))
                except (TimeoutError, asyncio.CancelledError):
                    return False
                finally:
                    rec.pending.pop(req_id, None)
                    if rec.status == "waiting_approval":
                        rec.status = "running"

            await run_loop(provider=provider, session=rec.session,
                           task=task_text, config=cfg, store=store(),
                           cache=None, policy=policy, approve=approve)
            rec.status = "done"
        except Exception as e:  # surface crash state; events keep the truth
            rec.status = "error"
            rec.error = f"{type(e).__name__}: {e}"

    def _summary(rec: SessionRecord) -> dict[str, Any]:
        return {"id": rec.id, "source": rec.source, "task": rec.task,
                "status": rec.status, "error": rec.error,
                "pending_approvals": sorted(rec.pending)}

    @app.post("/sessions")
    async def create_session(body: CreateBody) -> dict[str, Any]:
        if not Path(body.repo).exists():
            raise HTTPException(400, f"repo not found: {body.repo}")
        rec = reg().create(body.repo, body.task, dict(body.config),
                           body.provider)
        if "token_budget" not in rec.config and body.token_budget is not None:
            rec.config["token_budget"] = body.token_budget
        out = _summary(rec)
        if body.task:
            rec.run_task = asyncio.create_task(_run_session(rec, body.task))
            out["status"] = rec.status
        return out

    @app.get("/sessions")
    async def list_sessions() -> list[dict[str, Any]]:
        return [_summary(r) for r in reg().list()]

    @app.get("/sessions/{sid}")
    async def get_session(sid: str) -> dict[str, Any]:
        rec = reg().get(sid)
        if rec is None:
            raise HTTPException(404, "unknown session")
        return _summary(rec)

    @app.post("/sessions/{sid}/messages")
    async def post_message(sid: str, body: MessageBody) -> dict[str, Any]:
        rec = reg().get(sid)
        if rec is None:
            raise HTTPException(404, "unknown session")
        if rec.status in ("running", "waiting_approval"):
            raise HTTPException(409, "session already running")
        rec.run_task = asyncio.create_task(_run_session(rec, body.content))
        return _summary(rec)

    @app.get("/sessions/{sid}/events")
    async def get_events(
        sid: str, since_seq: int = Query(0, ge=0)
    ) -> list[dict[str, Any]]:
        rec = reg().get(sid)
        if rec is None:
            raise HTTPException(404, "unknown session")
        return [e.model_dump(mode="json") for e in store().read(sid)
                if e.seq >= since_seq]

    @app.get("/sessions/{sid}/diff")
    async def get_diff(sid: str) -> dict[str, str]:
        rec = reg().get(sid)
        if rec is None or rec.session is None:
            raise HTTPException(404, "unknown session or no workspace yet")
        return {"diff": rec.session.get_diff()}

    @app.post("/sessions/{sid}/approvals/{req_id}")
    async def decide_approval(sid: str, req_id: str,
                              body: ApprovalBody) -> dict[str, Any]:
        rec = reg().get(sid)
        if rec is None:
            raise HTTPException(404, "unknown session")
        # The request event is emitted just before the resolver registers its
        # future; tolerate that millisecond gap instead of 404ing it.
        fut = None
        for _ in range(50):
            fut = rec.pending.get(req_id)
            if fut is not None and not fut.done():
                break
            fut = None
            await asyncio.sleep(0.2)
        if fut is None:
            raise HTTPException(404, "no such pending approval")
        fut.set_result(bool(body.allow))
        return {"id": req_id, "allow": bool(body.allow)}

    @app.post("/sessions/{sid}/fork")
    async def fork_session(sid: str, at_seq: int | None = None) -> dict[str, Any]:
        rec = reg().get(sid)
        if rec is None:
            raise HTTPException(404, "unknown session")
        if rec.status in ("running", "waiting_approval"):
            raise HTTPException(409, "cannot fork a running session")
        prefix = [e for e in store().read(sid)
                  if at_seq is None or e.seq <= at_seq]
        child = reg().create(rec.source, None, dict(rec.config), rec.provider)
        for e in prefix:
            store().append(Event(session_id=child.id, seq=0, type=e.type,
                                 data=e.data))
        return _summary(child)

    @app.get("/sessions/{sid}/stream")
    async def stream_events(sid: str) -> EventSourceResponse:
        rec = reg().get(sid)
        if rec is None:
            raise HTTPException(404, "unknown session")

        from collections.abc import AsyncIterator

        async def gen() -> AsyncIterator[dict[str, str]]:
            import time

            seen = -1
            start = time.monotonic()
            ended = False
            while True:
                if time.monotonic() - start > STREAM_TIMEOUT_S:
                    break
                fresh = [e for e in store().read(sid) if e.seq > seen]
                for e in fresh:
                    seen = e.seq
                    yield {"event": e.type, "id": str(e.seq),
                           "data": e.model_dump_json()}
                    if e.type == "session_end":
                        ended = True
                if ended:
                    break
                await asyncio.sleep(STREAM_POLL_S)

        return EventSourceResponse(gen())

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/eval-summary")
    async def eval_summary() -> dict[str, Any]:
        """Analyze --summary-json outputs for the dashboard. {} when none."""
        return await asyncio.to_thread(_read_summaries, str(app.state.root))

    @app.exception_handler(Exception)
    async def _errors(request: Any, exc: Exception) -> JSONResponse:
        if isinstance(exc, HTTPException):
            raise exc
        return JSONResponse({"detail": f"{type(exc).__name__}: {exc}"},
                            status_code=500)

    return app
