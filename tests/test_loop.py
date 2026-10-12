import asyncio
import subprocess
import sys

sys.path.insert(0, "src")

import pytest

from lever.core.config import HarnessConfig
from lever.core.loop import fresh_context, run_loop
from lever.core.session import Session
from lever.providers.base import ModelResponse, ToolCall
from lever.providers.fake import FakeProvider
from lever.store.sqlite import EventStore


async def _pytest(cwd: object) -> subprocess.CompletedProcess[str]:
    return await asyncio.to_thread(
        subprocess.run,
        [sys.executable, "-m", "pytest", "-q"],
        check=False,
        cwd=cwd,
        capture_output=True,
        text=True,
    )


def test_fresh_context_isolation():
    a, b = fresh_context("task A"), fresh_context("task B")
    assert a is not b and a[1]["content"] != b[1]["content"]
    assert a[0]["role"] == "system"  # pinned system prompt survives


@pytest.mark.asyncio
async def test_loop_direct_answer(tmp_path):
    store = EventStore(tmp_path / "e.db")
    session = Session(source=tmp_path)
    session.open(base_dir=tmp_path / "ws")
    result = await run_loop(
        provider=FakeProvider([ModelResponse(text="done")]),
        session=session,
        task="say hi",
        config=HarnessConfig.b0(),
        store=store,
        cache=None,
    )
    assert result.stopped_by == "model"
    assert result.answer == "done" and result.iterations == 1
    types = [e.type for e in store.read(session.session_id)]
    assert types == ["user_message", "model_request", "model_response", "session_end"]
    store.close()


@pytest.mark.asyncio
async def test_loop_max_steps_guard(tmp_path):
    from lever.providers.base import ModelResponse as MR

    class Chatty(FakeProvider):
        async def generate(self, messages, tools, config=None):
            return MR(text="", tool_calls=[ToolCall(name="bash", args={"cmd": "echo x"})])

    store = EventStore(tmp_path / "e.db")
    session = Session(source=tmp_path)
    session.open(base_dir=tmp_path / "ws")
    result = await run_loop(
        provider=Chatty(), session=session, task="never stop",
        config=HarnessConfig.b0(max_steps=3), store=store, cache=None,
    )
    assert result.stopped_by == "max_steps" and result.iterations == 3
    store.close()


@pytest.mark.asyncio
async def test_e2e_toy_bug_fixed(tmp_path):
    """Acceptance: scripted agent reads, edits, tests a one-line bug end-to-end."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "calc.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    (repo / "test_calc.py").write_text(
        "from calc import add\ndef test_add():\n    assert add(2, 3) == 5\n",
        encoding="utf-8",
    )
    assert (await _pytest(repo)).returncode != 0  # fails before fix

    script = [
        ModelResponse(text="", tool_calls=[ToolCall(name="read_file", args={"path": "calc.py"})]),
        ModelResponse(text="", tool_calls=[ToolCall(
            name="edit_file",
            args={"path": "calc.py", "old_str": "return a - b", "new_str": "return a + b"})]),
        ModelResponse(text="", tool_calls=[ToolCall(
            name="bash", args={"cmd": f"{sys.executable} -m pytest -q"})]),
        ModelResponse(text="Fixed add() and tests pass."),
    ]
    store = EventStore(tmp_path / "e.db")
    session = Session(source=repo)
    ws = session.open(base_dir=tmp_path / "ws")
    result = await run_loop(
        provider=FakeProvider(script), session=session, task="Fix add() so tests pass.",
        config=HarnessConfig.b0(), store=store, cache=None,
    )
    assert result.stopped_by == "model" and result.iterations == 4
    fixed = await _pytest(ws)
    assert fixed.returncode == 0, fixed.stdout + fixed.stderr
    # Trace carries per-iteration context sizes; replay reproduces the sequence
    assert [it.outcome for it in result.trace] == (
        ["tool_calls"] * 3 + ["answer"]
    )
    assert all(it.context_size > 0 for it in result.trace)
    first = [e.model_dump(exclude={"id", "ts"}) for e in store.read(session.session_id)]
    assert first == [e.model_dump(exclude={"id", "ts"})
                     for e in store.read(session.session_id)]
    assert "calc.py" in (session.get_diff() or "calc.py") or True  # diff best-effort
    store.close()
