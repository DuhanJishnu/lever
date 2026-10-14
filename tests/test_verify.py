import sys

sys.path.insert(0, "src")

import pytest

from lever.core.config import HarnessConfig
from lever.core.loop import run_loop
from lever.core.session import Session
from lever.core.verify import (
    VERIFY_MAX_ROUNDS,
    detect_test_cmd,
    mentioned_files,
    run_tests,
    trace_ran_tests,
    verify_completion,
)
from lever.providers.base import ModelResponse, ToolCall
from lever.providers.fake import FakeProvider
from lever.store.sqlite import EventStore


def _repo(tmp_path, buggy=True):
    body = "return a - b\n" if buggy else "return a + b\n"
    (tmp_path / "calc.py").write_text(f"def add(a, b):\n    {body}", encoding="utf-8")
    (tmp_path / "test_calc.py").write_text(
        "from calc import add\ndef test_add():\n    assert add(2, 3) == 5\n",
        encoding="utf-8",
    )
    return tmp_path


def test_detect_test_cmd(tmp_path):
    assert detect_test_cmd(tmp_path) is None
    (tmp_path / "m.py").write_text("x = 1\n", encoding="utf-8")
    cmd = detect_test_cmd(tmp_path)
    assert cmd is not None and "compileall" in cmd
    (tmp_path / "test_m.py").write_text("def test_x():\n    pass\n", encoding="utf-8")
    cmd = detect_test_cmd(tmp_path)
    assert cmd is not None and "pytest" in cmd


@pytest.mark.asyncio
async def test_run_tests_pass_fail(tmp_path):
    import shutil

    _repo(tmp_path, buggy=True)
    passed, report, cmd = await run_tests(tmp_path)
    assert passed is False and "FAILED" in report and cmd
    # same-second rewrites keep stale bytecode: drop caches between phases
    shutil.rmtree(tmp_path / "__pycache__", ignore_errors=True)
    shutil.rmtree(tmp_path / ".pytest_cache", ignore_errors=True)
    _repo(tmp_path, buggy=False)
    passed, report, cmd = await run_tests(tmp_path)
    assert passed is True and "passed" in report


def test_trace_and_mentions():
    from lever.core.loop import LoopIteration, ToolEvent

    trace = [LoopIteration(index=1, outcome="tool_calls", tool_events=[
        ToolEvent(tool="bash", args={"cmd": "python -m pytest -q"}, result="x")])]
    assert trace_ran_tests(trace) is True
    assert trace_ran_tests([]) is False
    assert mentioned_files("see add.py and missing.py ok") == ["add.py", "missing.py"]


@pytest.mark.asyncio
async def test_verify_completion_marks(tmp_path):
    _repo(tmp_path, buggy=False)
    vr = await verify_completion(tmp_path, "fixed calc.py, see nope.py", trace=[])
    assert vr.passed is True
    assert vr.missing_files == ["nope.py"]
    assert vr.ran_tests_in_trace is False
    assert "never invoked" in vr.report


@pytest.mark.asyncio
async def test_loop_accepts_verified_done(tmp_path):
    _repo(tmp_path, buggy=True)
    script = [
        ModelResponse(text="", tool_calls=[ToolCall(
            name="edit_file",
            args={"path": "calc.py", "old_str": "return a - b",
                  "new_str": "return a + b"})]),
        ModelResponse(text="Fixed!"),
    ]
    store = EventStore(tmp_path / "e.db")
    session = Session(source=tmp_path)
    session.open(base_dir=tmp_path / "ws")
    cfg = HarnessConfig.b0(verify_loop=True)
    result = await run_loop(provider=FakeProvider(script), session=session,
                            task="fix it", config=cfg, store=store, cache=None)
    assert result.answer == "Fixed!"
    kinds = [e.data.get("name") for e in store.read(session.session_id)
             if e.type == "tool_call"]
    assert kinds.count("verify_tests") == 1
    store.close()


@pytest.mark.asyncio
async def test_loop_rejects_then_accepts(tmp_path):
    _repo(tmp_path, buggy=True)
    script = [
        ModelResponse(text="All done, trust me."),  # premature claim
        ModelResponse(text="", tool_calls=[ToolCall(
            name="edit_file",
            args={"path": "calc.py", "old_str": "return a - b",
                  "new_str": "return a + b"})]),
        ModelResponse(text="Now really fixed."),
    ]
    store = EventStore(tmp_path / "e.db")
    session = Session(source=tmp_path)
    session.open(base_dir=tmp_path / "ws")
    cfg = HarnessConfig.b0(verify_loop=True)
    prov = FakeProvider(script)
    result = await run_loop(provider=prov, session=session,
                            task="fix it", config=cfg, store=store, cache=None)
    assert result.answer == "Now really fixed."
    kinds = [e.data.get("name") for e in store.read(session.session_id)
             if e.type == "tool_call"]
    assert kinds.count("verify_tests") == 2
    # the model saw the failure feedback before its fix turn
    third_input = prov.calls[2]["messages"]
    assert any("[verify]" in str(m.get("content", "")) for m in third_input)
    assert VERIFY_MAX_ROUNDS == 3
    store.close()
