import sys
from types import SimpleNamespace

sys.path.insert(0, "src")

import pytest

from lever.prompts.registry import available_versions, render_system
from lever.tools.registry import create_tools


def test_prompt_versions_exist():
    assert set(available_versions()) >= {"v1", "v2"}
    assert render_system("nope", ["a"]) == render_system("v1", ["a"])


def test_v1_v2_render():
    v1 = render_system("v1", ["read_file", "bash"])
    assert "read_file, bash" in v1 and "todo" not in v1
    v2 = render_system("v2", ["read_file", "todo"])
    for token in ("EXPLORE", "PLAN", "VERIFY", "todo", "Example 1"):
        assert token in v2


def test_todo_tool_round_trip(tmp_path):
    import asyncio

    reg = create_tools(tmp_path, SimpleNamespace(planner_prompt=True))
    assert "todo" in reg.by_name
    assert "empty" in asyncio.run(reg.run("todo", {"action": "list"}))
    asyncio.run(reg.run("todo", {"action": "add", "item": "read files"}))
    asyncio.run(reg.run("todo", {"action": "add", "item": "fix bug"}))
    out = asyncio.run(reg.run("todo", {"action": "done", "index": 1}))
    assert "1. [x] read files" in out and "2. [ ] fix bug" in out
    assert "out of range" in asyncio.run(
        reg.run("todo", {"action": "done", "index": 9}))
    assert "unknown action" in asyncio.run(reg.run("todo", {"action": "nap"}))
    assert "cleared" in asyncio.run(reg.run("todo", {"action": "clear"}))


def test_todo_absent_without_flag(tmp_path):
    assert "todo" not in create_tools(tmp_path).by_name
    reg = create_tools(tmp_path, SimpleNamespace())
    assert "todo" not in reg.by_name


def test_todo_state_is_per_session(tmp_path):
    import asyncio

    a = create_tools(tmp_path, SimpleNamespace(planner_prompt=True))
    b = create_tools(tmp_path, SimpleNamespace(planner_prompt=True))
    asyncio.run(a.run("todo", {"action": "add", "item": "x"}))
    assert "empty" in asyncio.run(b.run("todo", {"action": "list"}))


@pytest.mark.asyncio
async def test_loop_uses_v2_and_todo(tmp_path):
    from lever.core.config import HarnessConfig
    from lever.core.loop import run_loop, select_prompt_version
    from lever.core.session import Session
    from lever.providers.base import ModelResponse
    from lever.providers.fake import FakeProvider
    from lever.store.sqlite import EventStore

    assert select_prompt_version(HarnessConfig.b0()) == "v1"
    assert select_prompt_version(HarnessConfig.b0(planner_prompt=True)) == "v2"
    prov = FakeProvider([ModelResponse(text="done")])
    store = EventStore(tmp_path / "e.db")
    session = Session(source=tmp_path)
    session.open(base_dir=tmp_path / "ws")
    cfg = HarnessConfig.b0(planner_prompt=True, prompt_version="v2")
    await run_loop(provider=prov, session=session, task="t",
                   config=cfg, store=store, cache=None)
    first_system = prov.calls[0]["messages"][0]["content"]
    assert "PLAN" in first_system and "todo" in first_system
    store.close()
