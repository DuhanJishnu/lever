"""Headless CLI: `lever run --repo ./path --task "..." [--config b0.yaml]`.

Prints the session's events as JSON lines (the future event-stream protocol).
Human summary goes to stderr so stdout stays machine-readable.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import typer
from dotenv import load_dotenv

app = typer.Typer()


def _load_config(spec: str) -> Any:
    from lever.core.config import HarnessConfig

    base = HarnessConfig.b0()
    p = Path(spec)
    if p.suffix in (".yaml", ".yml", ".json") and p.exists():
        if p.suffix == ".json":
            data = json.loads(p.read_text(encoding="utf-8"))
        else:
            import yaml

            data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        return base.model_copy(update=data)
    if spec != "b0":
        raise typer.BadParameter(f"Unknown preset {spec!r} (use 'b0' or a file path).")
    return base


@app.command("sessions")
def sessions(
    db: str = typer.Option(".lever_events.db", help="SQLite event-store path."),
) -> None:
    """List sessions in the event store (id, events, last type)."""
    import sqlite3

    conn = sqlite3.connect(db)
    rows = conn.execute(
        "SELECT session_id, COUNT(*), MAX(seq) FROM events GROUP BY session_id "
        "ORDER BY MAX(seq) DESC"
    ).fetchall()
    if not rows:
        typer.echo("(no sessions)")
    for sid, count, last_seq in rows:
        typer.echo(f"{sid} events={count} last_seq={last_seq}")
    conn.close()


@app.command("run")
def run(
    repo: str = typer.Option(..., help="Path to the source repo to work on."),
    task: str = typer.Option(..., help="Task description (issue-style)."),
    config: str = typer.Option("b0", help="Preset ('b0') or path to yaml/json overrides."),
    db: str = typer.Option(".lever_events.db", help="SQLite event-store path."),
    cache_path: str = typer.Option(".lever_cache.jsonl", help="LLM response cache path."),
    fake: bool = typer.Option(False, "--fake", help="Use FakeProvider (no API key)."),
    provider: str = typer.Option("auto", help="auto|fake|gemini|local (local = llama-server, free)."),
    max_steps: int | None = typer.Option(None, help="Override max_steps."),
) -> None:
    load_dotenv()
    import os

    from lever.core.loop import run_loop
    from lever.core.session import Session
    from lever.providers.cache import ResponseCache
    from lever.store.sqlite import EventStore

    cfg = _load_config(config)
    if max_steps:
        cfg = cfg.model_copy(update={"max_steps": max_steps})

    if provider == "local":
        from lever.providers.local import LocalProvider

        provider_any: Any = LocalProvider()
    elif provider == "fake" or fake or (
            provider == "auto" and not os.getenv("GEMINI_API_KEY")):
        from lever.providers.fake import FakeProvider

        provider_any = FakeProvider.say_hi()
    else:
        from lever.providers.gemini import GeminiProvider

        provider_any = GeminiProvider()

    store = EventStore(db)
    session = Session(source=Path(repo))
    session.open()
    result = asyncio.run(
        run_loop(provider=provider_any, session=session, task=task,
                 config=cfg, store=store, cache=ResponseCache(cache_path))
    )
    for ev in store.read(session.session_id):
        print(ev.model_dump_json())
    typer.echo(
        f"session={session.session_id} stopped_by={result.stopped_by} "
        f"iterations={result.iterations} answer={result.answer} "
        f"diff_stat={session.get_diff()!r}",
        err=True,
    )
    store.close()


@app.command("serve")
def serve(
    port: int = typer.Option(8000, help="Port to listen on."),
    db: str = typer.Option(".lever_sessions.db", help="Sessions event-store path."),
) -> None:
    """Start the Lever HTTP server (REST + SSE) for the web UI."""
    load_dotenv()
    import uvicorn

    from lever.server.app import create_app

    uvicorn.run(create_app(db), host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    sys.exit(app())
