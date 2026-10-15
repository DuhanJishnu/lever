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
    model: str | None = None
    token_budget: int | None = None


class MessageBody(BaseModel):
    content: str
    files: list[str] = []


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


def _provider(kind: str, custom: dict[str, Any] | None = None,
              model: str | None = None) -> tuple[Any, str]:
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

        gemini: Any = GeminiProvider(model=model)
        return gemini, str(gemini.model)
    # auto: gemini when keyed, else fake (never spends by accident)
    import os

    if os.getenv("GEMINI_API_KEY"):
        from ..providers.gemini import GeminiProvider

        auto: Any = GeminiProvider(model=model)
        return auto, str(auto.model)
    from ..providers.fake import FakeProvider

    return FakeProvider.say_hi(), "fake"


def _config(overrides: dict[str, Any]) -> HarnessConfig:
    # Interactive serve defaults: tolerant edits + loop guard on.
    # Evals still pin exact behaviour via explicit overrides (see evals/configs.json);
    # HarnessConfig.b0() itself stays all-off for the ladder.
    base = HarnessConfig.b0()
    defaults: dict[str, Any] = {"tolerant_edit": True, "loop_guard": True,
                                "verify_loop": True}
    defaults.update(overrides or {})
    return base.model_copy(update=defaults)


SKIP_TREE_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache",
                  ".ruff_cache", "node_modules", ".mypy_cache"}
MAX_TREE_ENTRIES = 2000
MAX_FILE_CHARS = 100_000


def rec_or_404(reg: Registry, sid: str) -> SessionRecord:
    rec = reg.get(sid)
    if rec is None or rec.session is None or rec.session.workspace is None:
        raise HTTPException(404, "unknown session or no workspace yet")
    return rec


def _tree(workspace: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []

    def walk(dirpath: Path, rel: str, depth: int) -> None:
        if len(out) >= MAX_TREE_ENTRIES or depth > 6:
            return
        try:
            entries = sorted(dirpath.iterdir(),
                             key=lambda p: (p.is_file(), p.name.lower()))
        except OSError:
            return
        for p in entries:
            if p.name in SKIP_TREE_DIRS or len(out) >= MAX_TREE_ENTRIES:
                continue
            r = f"{rel}{p.name}"
            if p.is_dir():
                out.append({"path": r, "type": "dir"})
                walk(p, r + "/", depth + 1)
            elif p.is_file():
                try:
                    size = p.stat().st_size
                except OSError:
                    continue
                out.append({"path": r, "type": "file", "size": size})

    walk(workspace, "", 0)
    return out


def _resolve_ws(rec: SessionRecord, rel: str) -> Path:
    assert rec.session is not None and rec.session.workspace is not None
    root = rec.session.workspace.resolve()
    target = (root / rel).resolve()
    if target != root and not target.is_relative_to(root):
        raise HTTPException(400, f"path escapes workspace: {rel!r}")
    return target


def _read_ws_file(rec: SessionRecord, rel: str) -> tuple[str, bool]:
    target = _resolve_ws(rec, rel)
    if not target.is_file():
        raise HTTPException(404, f"no such file: {rel!r}")
    try:
        raw = target.read_bytes()
    except OSError as e:
        raise HTTPException(400, f"unreadable file: {e}")
    if b"\x00" in raw[:4096]:
        return "(binary file, not shown)", True
    text = raw.decode("utf-8", errors="replace")
    if len(text) > MAX_FILE_CHARS:
        return (text[:MAX_FILE_CHARS]
                + f"\n[... truncated at {MAX_FILE_CHARS} chars ...]"), True
    return text, False


def _git_show(rec: SessionRecord, rel: str) -> str | None:
    """Baseline-committed content (None when the file is new/untracked)."""
    import subprocess

    assert rec.session is not None and rec.session.workspace is not None
    try:
        proc = subprocess.run(
            ["git", "show", f"HEAD:{rel.replace(chr(92), '/')}"],
            check=False, cwd=rec.session.workspace,
            capture_output=True, timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.decode("utf-8", errors="replace")


def _workspace_snapshot(rec: SessionRecord, limit: int = 100) -> str:
    """File list + git status for follow-ups so the model edits in place.

    Follow-up runs start from a fresh LLM context (see loop.fresh_context),
    so without this the model cannot resolve "my add function" to add.py
    and invents canonical names like my_script.py.
    """
    assert rec.session is not None and rec.session.workspace is not None
    try:
        entries = _tree(rec.session.workspace)
        files = [e["path"] for e in entries if e.get("type") == "file"][:limit]
    except (OSError, ValueError):
        files = []
    try:
        diff = rec.session.get_diff()
    except (OSError, ValueError):
        diff = ""
    lines = ["Workspace files (edit these in place, do not invent new filenames):"]
    lines += [f"- {p}" for p in files] if files else ["- (empty)"]
    if diff.strip():
        lines.append("\nCurrent changes (git diff --stat + status):\n" + diff.strip())
    else:
        lines.append("\nCurrent changes: none yet")
    lines.append("\nRule: only edit existing files listed above. Never create a new file "
                 "unless the user explicitly asks for a new file. "
                 "Use read/grep to locate the function first.")
    return "\n".join(lines)


def _prior_history(store: Any, sid: str, limit: int = 6) -> str:
    """Prior user tasks + final answers so 'my add function' stays grounded."""
    try:
        events = store.read(sid)
    except (OSError, ValueError):
        return ""
    users = [str(e.data.get("content", "")) for e in events
             if e.type == "user_message"]
    answers = [str(e.data.get("answer", "")) for e in events
               if e.type == "session_end" and e.data.get("answer")]
    if not users and not answers:
        return ""
    parts = ["Prior conversation (same workspace, edits accumulate):"]
    for i, (u, a) in enumerate(zip(users[-limit:], answers[-limit:] + [""] * limit)):
        if u:
            parts.append(f"- task {i + 1}: {u[:1000]}")
        if a:
            parts.append(f"  result: {a[:1000]}")
    # dangling user messages without a paired answer yet
    if len(users) > len(answers):
        for u in users[len(answers):][-limit:]:
            if u not in " ".join(parts):
                parts.append(f"- task: {u[:1000]}")
    return "\n".join(parts)


def _with_attachments(rec: SessionRecord, content: str,
                      rels: list[str], snapshot: str = "",
                      history: str = "") -> str:
    """Build a follow-up task: workspace snapshot + history + files + instruction.

    Same workspace persists across runs, so edits accumulate — the
    interactive loop. Big files truncate with a marker (never silent).
    Snapshot/history are always included (even with no @-files) so a bare
    "change my add function" still resolves to the existing file.
    """
    parts = []
    if history.strip():
        parts.append(history.strip())
    if snapshot.strip():
        parts.append(snapshot.strip())
    if rels:
        attached = []
        for rel in rels[:10]:  # hard cap: 10 files per message
            try:
                text, truncated = _read_ws_file(rec, rel)
            except HTTPException as e:
                text, truncated = f"(unreadable: {e.detail})", True
            note = " (truncated)" if truncated else ""
            attached.append(f"=== {rel}{note} ===\n{text}")
        parts.append("Context files (already in your workspace):\n\n"
                     + "\n\n".join(attached))
    parts.append(f"Task: {content}")
    return "\n\n".join(parts)


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

    from ..core.session import Session as _Session

    def ensure_workspace(rec: SessionRecord) -> Path:
        if rec.session is None:
            rec.session = _Session(source=Path(rec.source))
            rec.session.session_id = rec.id
            rec.session.open()
        assert rec.session.workspace is not None
        return rec.session.workspace

    async def _run_session(rec: SessionRecord, task_text: str) -> None:
        from ..core.loop import run_loop

        rec.status = "running"
        rec.task = task_text
        try:
            workspace = ensure_workspace(rec)
            assert rec.session is not None
            provider, model_name = _provider(
                rec.provider, app.state.providers, rec.model)
            rec.model = model_name
            cfg = _config(rec.config)
            policy = _policy(workspace, rec.config.get("token_budget"))
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
                "model": rec.model, "provider": rec.provider,
                "pending_approvals": sorted(rec.pending)}

    @app.post("/sessions")
    async def create_session(body: CreateBody) -> dict[str, Any]:
        if not Path(body.repo).exists():
            raise HTTPException(400, f"repo not found: {body.repo}")
        rec = reg().create(body.repo, body.task, dict(body.config),
                           body.provider)
        rec.model = body.model or ""
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

    def _with_attachments_open(rec: SessionRecord, content: str,
                                 rels: list[str]) -> str:
        ensure_workspace(rec)
        snapshot = _workspace_snapshot(rec)
        history = _prior_history(store(), rec.id)
        return _with_attachments(rec, content, rels, snapshot, history)

    @app.post("/sessions/{sid}/messages")
    async def post_message(sid: str, body: MessageBody) -> dict[str, Any]:
        rec = reg().get(sid)
        if rec is None:
            raise HTTPException(404, "unknown session")
        if rec.status in ("running", "waiting_approval"):
            raise HTTPException(409, "session already running")
        task_text = _with_attachments_open(rec, body.content, body.files)
        rec.run_task = asyncio.create_task(_run_session(rec, task_text))
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

    @app.get("/providers")
    async def list_providers() -> list[dict[str, Any]]:
        """Model/provider picker for the UI: id, display model, configured?"""
        import os

        return [
            {"id": "auto", "model": "auto",
             "configured": True, "cost": "decided by env"},
            {"id": "fake", "model": "fake (scripted)",
             "configured": True, "cost": "$0"},
            {"id": "local", "model": os.getenv("LEVER_LOCAL_MODEL", ""),
             "configured": bool(os.getenv("LEVER_LOCAL_MODEL")), "cost": "$0"},
            {"id": "gemini", "model": os.getenv("LEVER_MODEL", ""),
             "configured": bool(os.getenv("GEMINI_API_KEY")), "cost": "metered"},
        ]

    @app.get("/sessions/{sid}/files")
    async def list_files(sid: str) -> list[dict[str, Any]]:
        rec = reg().get(sid)
        if rec is None or rec.session is None or rec.session.workspace is None:
            raise HTTPException(404, "unknown session or no workspace yet")
        return _tree(rec.session.workspace)

    @app.get("/sessions/{sid}/file")
    async def get_file(sid: str, path: str = Query(...)) -> dict[str, Any]:
        content, truncated = _read_ws_file(rec_or_404(reg(), sid), path)
        return {"path": path, "content": content, "truncated": truncated}

    @app.get("/sessions/{sid}/file-diff")
    async def get_file_diff(sid: str, path: str = Query(...)) -> dict[str, Any]:
        rec = rec_or_404(reg(), sid)
        _content, _ = _read_ws_file(rec, path)
        original = _git_show(rec, path)
        return {"path": path, "original": original, "modified": _content}

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
