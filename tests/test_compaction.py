import sys

sys.path.insert(0, "src")

import pytest

from lever.context.compaction import (
    COMPACTION_THRESHOLD,
    compact_history,
    needs_compaction,
    split_tiers,
)
from lever.core.config import HarnessConfig
from lever.core.loop import run_loop
from lever.core.session import Session
from lever.providers.base import ModelResponse, ToolCall
from lever.providers.fake import FakeProvider
from lever.store.sqlite import EventStore


def _msgs(n_mid: int) -> list[dict]:
    msgs = [
        {"role": "system", "content": "SYSTEM"},
        {"role": "user", "content": "TASK"},
    ]
    for i in range(n_mid):
        msgs.append({"role": "assistant", "content": f"thought {i}"})
        msgs.append({"role": "tool", "name": "bash", "content": f"out {i}"})
    return msgs


def test_threshold_math():
    assert needs_compaction(700, 1000) is True
    assert needs_compaction(699, 1000) is False
    assert needs_compaction(10**9, 0) is False
    assert COMPACTION_THRESHOLD == 0.7


def test_split_tiers_pins_and_tails():
    pinned, middle, tail = split_tiers(_msgs(5))
    assert [m["content"] for m in pinned] == ["SYSTEM", "TASK"]
    assert len(tail) == 4
    assert len(middle) == 10 - 4
    pinned, middle, tail = split_tiers(_msgs(1))
    assert middle == [] and len(tail) == 2  # nothing to compact: no-op


@pytest.mark.asyncio
async def test_compact_preserves_pinned():
    prov = FakeProvider([ModelResponse(text="GOAL: x\nNEXT STEPS: y")])
    msgs = _msgs(5)
    # fatten middle so shrinking is arithmetic, not just structural
    for m in msgs[2:]:
        m["content"] = str(m.get("content", "")) + "x" * 500
    shrunk, info = await compact_history(msgs, prov, None)
    assert info is not None and info["before"] > info["after"]
    assert info["dropped"] == 6
    assert shrunk[0]["content"] == "SYSTEM" and shrunk[1]["content"] == "TASK"
    assert "GOAL: x" in shrunk[2]["content"]
    assert prov.calls[0]["messages"][0]["content"].startswith("Summarize")
    # summary call carries no tools
    assert len(prov.calls) == 1


@pytest.mark.asyncio
async def test_compact_noop_without_middle():
    prov = FakeProvider([ModelResponse(text="unused")])
    shrunk, info = await compact_history(_msgs(1), prov, None)
    assert info is None and shrunk == _msgs(1)
    assert prov.calls == []  # no provider call spent


@pytest.mark.asyncio
async def test_loop_emits_compacted_event(tmp_path, monkeypatch):
    # Tripwire forced: estimate always huge, so compaction fires whenever
    # middle exists — deterministic regardless of token arithmetic.
    import lever.core.loop as loop_mod

    monkeypatch.setattr(loop_mod, "estimate_tokens", lambda messages: 100_000)
    # Middle exists only past 6 messages (2 pinned + 4 tail): compaction can
    # first fire on turn 4, so the NOTE sits at script[3].
    script = [
        ModelResponse(text="", tool_calls=[ToolCall(name="bash", args={"cmd": "echo a"})]),
        ModelResponse(text="", tool_calls=[ToolCall(name="bash", args={"cmd": "echo b"})]),
        ModelResponse(text="", tool_calls=[ToolCall(name="bash", args={"cmd": "echo c"})]),
        ModelResponse(text="GOAL: t\nNEXT STEPS: fix"),
        ModelResponse(text="done"),
    ]
    store = EventStore(tmp_path / "e.db")
    session = Session(source=tmp_path)
    session.open(base_dir=tmp_path / "ws")
    cfg = HarnessConfig.b0(max_steps=8, compaction=True)
    result = await run_loop(provider=FakeProvider(script), session=session,
                            task="tiny task", config=cfg, store=store, cache=None)
    assert result.answer == "done"
    compacted = [e for e in store.read(session.session_id)
                 if e.type == "context_compacted"]
    assert len(compacted) == 1
    assert all("before" in e.data and "after" in e.data for e in compacted)
    store.close()
