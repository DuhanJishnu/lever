"""SQLite event store (WAL mode): append(event), read(session_id).

Thread-safe: one connection with check_same_thread=False guarded by a lock,
so FastAPI endpoints, background run tasks, and SSE streams can share it.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import cast

from ..core.events import Event, EventType

_SCHEMA = (Path(__file__).parent / "schema.sql").read_text(encoding="utf-8")


class EventStore:
    def __init__(self, path: str | Path = ".lever_events.db") -> None:
        self.path = Path(path)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL;")
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    def append(self, event: Event) -> Event:
        """Assign next seq for the session and persist. Returns event with id/seq."""
        with self._lock:
            cur = self._conn.execute(
                "SELECT COALESCE(MAX(seq), -1) FROM events WHERE session_id = ?",
                (event.session_id,),
            )
            nxt = int(cur.fetchone()[0]) + 1
            event.seq = nxt
            cur = self._conn.execute(
                "INSERT INTO events (session_id, seq, ts, type, data) VALUES (?, ?, ?, ?, ?)",
                (
                    event.session_id,
                    event.seq,
                    event.ts,
                    event.type,
                    json.dumps(event.data, default=str),
                ),
            )
            event.id = int(cur.lastrowid or 0)
            self._conn.commit()
            return event

    def read(self, session_id: str) -> list[Event]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT id, session_id, seq, ts, type, data FROM events "
                "WHERE session_id = ? ORDER BY seq",
                (session_id,),
            )
            rows = cur.fetchall()
        out: list[Event] = []
        for eid, sid, seq, ts, typ, data in rows:
            out.append(
                Event(
                    id=eid,
                    session_id=sid,
                    seq=seq,
                    ts=ts,
                    type=cast(EventType, typ),
                    data=json.loads(data),
                )
            )
        return out

    def close(self) -> None:
        with self._lock:
            self._conn.close()

