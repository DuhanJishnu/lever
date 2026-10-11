import sys

sys.path.insert(0, "src")

from lever.core.events import Event
from lever.store.sqlite import EventStore


def test_append_and_read_order(tmp_path):
    store = EventStore(tmp_path / "t.db")
    sid = "abc123"
    store.append(Event(session_id=sid, seq=0, type="user_message", data={"a": 1}))
    store.append(Event(session_id=sid, seq=0, type="model_response", data={"a": 2}))
    events = store.read(sid)
    assert [e.seq for e in events] == [0, 1]
    assert [e.type for e in events] == ["user_message", "model_response"]
    assert events[0].id is not None
    # Replay reproduces same sequence
    assert [e.model_dump(exclude={"id", "ts"}) for e in events] == [
        e.model_dump(exclude={"id", "ts"}) for e in store.read(sid)
    ]
    store.close()
