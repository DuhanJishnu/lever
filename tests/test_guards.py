import sys

sys.path.insert(0, "src")

import pytest

from lever.core.config import HarnessConfig
from lever.core.guards import (
    LoopState,
    RepeatTracker,
    call_key,
    compose_guards,
    is_failure,
    max_context_messages,
    max_steps_guard,
    max_tokens_guard,
    time_limit_guard,
)
from lever.core.loop import run_loop
from lever.core.session import Session
from lever.providers.base import ModelResponse, ToolCall
from lever.providers.fake import FakeProvider
from lever.store.sqlite import EventStore


def _state(**kw):
    base = {"iterations": 0, "max_steps": 40}
    base.update(kw)
    return LoopState(**base)


def test_hard_guards_fire():
    assert max_steps_guard(_state(iterations=40)).verdict == "stop"
    assert max_steps_guard(_state(iterations=39)).verdict == "continue"
    assert max_context_messages(10)(_state(context_messages=10)).verdict == "stop"
    assert max_tokens_guard(100)(_state(est_tokens=500)).verdict == "stop"
    assert time_limit_guard(60.0)(_state(elapsed_s=61.0)).verdict == "stop"
    assert time_limit_guard(60.0)(_state(elapsed_s=5.0)).verdict == "continue"


def test_compose_first_stop_wins():
    g = compose_guards(max_steps_guard, time_limit_guard(10.0))
    r = g(_state(iterations=40, elapsed_s=999.0))
    assert r.verdict == "stop" and "max_steps" in r.reason


def test_call_key_stable():
    assert call_key("bash", {"cmd": "x", "t": 1}) == call_key("bash", {"t": 1, "cmd": "x"})
    assert call_key("bash", {"cmd": "x"}) != call_key("bash", {"cmd": "y"})


def test_is_failure_conservative():
    assert is_failure("Error in bash: boom")
    assert is_failure("edit_file: old_str not found, retry")
    assert is_failure("edit_file: REVERTED — bad syntax")
    assert not is_failure("No matches.")
    assert not is_failure("Edit applied.\n...")
    assert not is_failure("$ pytest\nexit=0\n3 passed")


def test_tracker_escalates_nudge_replan_stop():
    tr = RepeatTracker()
    key = ["bash:{\"cmd\": \"echo x\"}"]
    actions = [tr.update(key, False)[0] for _ in range(8)]
    # triggers on 3rd, 4th, 5th, 6th...: nudge, nudge, replan, stop, stop
    assert actions[:2] == ["none", "none"]
    assert actions[2:6] == ["nudge", "nudge", "replan", "stop"]


def test_tracker_failure_pairs():
    tr = RepeatTracker()
    a = ["read_file:{\"path\": \"a.py\"}"]
    b = ["read_file:{\"path\": \"b.py\"}"]
    assert tr.update(a, True)[0] == "none"   # first failure: no trigger yet
    assert tr.update(b, True)[0] == "nudge"  # pair of failed turns -> trigger


def test_tracker_varied_calls_never_trigger():
    tr = RepeatTracker()
    for i in range(10):
        assert tr.update([f"bash:{{\"cmd\": \"echo {i}\"}}"], False)[0] == "none"


@pytest.mark.asyncio
async def test_loop_guard_off_by_default(tmp_path):
    """Without the flag, repetition runs to max_steps (old behavior)."""
    script = [ModelResponse(text="", tool_calls=[
        ToolCall(name="bash", args={"cmd": "echo hi"})])] * 4
    store = EventStore(tmp_path / "e.db")
    session = Session(source=tmp_path)
    session.open(base_dir=tmp_path / "ws")
    result = await run_loop(
        provider=FakeProvider(script), session=session, task="t",
        config=HarnessConfig.b0(max_steps=4), store=store, cache=None)
    assert result.stopped_by == "max_steps"
    assert result.stop_reason == ""
    store.close()


@pytest.mark.asyncio
async def test_loop_guard_stops_repetition(tmp_path):
    script = [ModelResponse(text="", tool_calls=[
        ToolCall(name="bash", args={"cmd": "echo hi"})])] * 10
    store = EventStore(tmp_path / "e.db")
    session = Session(source=tmp_path)
    session.open(base_dir=tmp_path / "ws")
    cfg = HarnessConfig.b0(max_steps=40, loop_guard=True)
    result = await run_loop(
        provider=FakeProvider(script), session=session, task="t",
        config=cfg, store=store, cache=None)
    assert result.stopped_by == "guardrail"
    assert "repetition" in result.stop_reason
    assert result.iterations < 10  # stopped well before max_steps
    kinds = [e.data.get("kind") for e in store.read(session.session_id)
             if e.type == "harness_nudge"]
    assert kinds.count("nudge") == 2
    assert "replan" in kinds and "stop" in kinds
    store.close()


@pytest.mark.asyncio
async def test_loop_guard_nudge_visible_in_history(tmp_path):
    prov = FakeProvider([
        ModelResponse(text="", tool_calls=[ToolCall(name="bash", args={"cmd": "a"})]),
        ModelResponse(text="", tool_calls=[ToolCall(name="bash", args={"cmd": "a"})]),
        ModelResponse(text="", tool_calls=[ToolCall(name="bash", args={"cmd": "a"})]),
        ModelResponse(text="done"),
    ])
    store = EventStore(tmp_path / "e.db")
    session = Session(source=tmp_path)
    session.open(base_dir=tmp_path / "ws")
    cfg = HarnessConfig.b0(max_steps=10, loop_guard=True)
    result = await run_loop(provider=prov, session=session, task="t",
                            config=cfg, store=store, cache=None)
    assert result.answer == "done"
    # 4th provider call saw the nudge user message in its history
    fourth = prov.calls[3]["messages"]
    assert any(m.get("role") == "user" and "[harness]" in str(m.get("content", ""))
               for m in fourth)
    store.close()
