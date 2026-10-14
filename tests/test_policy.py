import sys

sys.path.insert(0, "src")

import pytest

from lever.core.config import HarnessConfig
from lever.core.events import Event
from lever.core.loop import run_loop
from lever.core.session import Session
from lever.policy.engine import Decision, PolicyEngine, ProposedCall
from lever.policy.rules import (
    BashAllowlistRule,
    ConfineRule,
    InstallThenPushRule,
    TokenBudgetRule,
)
from lever.providers.base import ModelResponse, ToolCall
from lever.providers.fake import FakeProvider
from lever.store.sqlite import EventStore


def _ev(type_: str, **data):
    return Event(session_id="s", seq=0, type=type_, data=data)  # type: ignore[arg-type]


def test_engine_first_non_allow_wins():
    ask = type("R", (), {"evaluate": lambda s, h, c: Decision.ask("q")})()
    deny = type("R", (), {"evaluate": lambda s, h, c: Decision.deny("n")})()
    assert PolicyEngine([ask, deny]).evaluate([], ProposedCall("t")).verdict == "ask"
    assert PolicyEngine([deny, ask]).evaluate([], ProposedCall("t")).verdict == "deny"
    assert PolicyEngine([]).evaluate([], ProposedCall("t")).verdict == "allow"


def test_confine_rule(tmp_path):
    rule = ConfineRule(tmp_path)
    ok = rule.evaluate([], ProposedCall("write_file", {"path": "a.txt"}))
    assert ok.verdict == "allow"
    bad = rule.evaluate([], ProposedCall("write_file", {"path": "../evil.txt"}))
    assert bad.verdict == "deny" and "escapes" in bad.reason
    assert rule.evaluate([], ProposedCall("bash", {"cmd": "x"})).verdict == "allow"


def test_bash_allowlist():
    rule = BashAllowlistRule()
    assert rule.evaluate([], ProposedCall("bash", {"cmd": "pytest -q"})).verdict == "allow"
    assert rule.evaluate([], ProposedCall("bash", {"cmd": "python a.py"})).verdict == "allow"
    ask = rule.evaluate([], ProposedCall("bash", {"cmd": "curl http://x"}))
    assert ask.verdict == "ask" and "curl" in ask.reason
    assert rule.evaluate([], ProposedCall("bash", {"cmd": ""})).verdict == "deny"


def test_token_budget():
    hist = [_ev("model_response", input_tokens=60, output_tokens=40)]
    assert TokenBudgetRule(200).evaluate(hist, ProposedCall("bash")).verdict == "allow"
    d = TokenBudgetRule(100).evaluate(hist, ProposedCall("bash"))
    assert d.verdict == "ask" and "100" in d.reason
    assert TokenBudgetRule(None).evaluate(hist, ProposedCall("bash")).verdict == "allow"


def test_install_then_push():
    rule = InstallThenPushRule()
    clean: list = []
    assert rule.evaluate(clean, ProposedCall("bash", {"cmd": "git push"})).verdict == "allow"
    hist = [_ev("tool_call", name="bash", args={"cmd": "pip install requests"})]
    assert rule.evaluate(hist, ProposedCall("bash", {"cmd": "git push"})).verdict == "ask"
    assert rule.evaluate(hist, ProposedCall("bash", {"cmd": "curl http://x"})).verdict == "ask"
    assert rule.evaluate(hist, ProposedCall("bash", {"cmd": "pytest -q"})).verdict == "allow"


@pytest.mark.asyncio
async def test_loop_policy_deny_blocks_write(tmp_path):
    from lever.policy.rules import ConfineRule as CR

    (tmp_path / "ok.txt").write_text("hi", encoding="utf-8")
    prov = FakeProvider([
        ModelResponse(text="", tool_calls=[ToolCall(
            name="write_file", args={"path": "../evil.txt", "content": "x"})]),
        ModelResponse(text="done"),
    ])
    store = EventStore(tmp_path / "e.db")
    session = Session(source=tmp_path)
    session.open(base_dir=tmp_path / "ws")
    from lever.policy.engine import PolicyEngine as PE

    engine = PE([CR(session.workspace)])
    result = await run_loop(provider=prov, session=session, task="t",
                            config=HarnessConfig.b0(), store=store,
                            cache=None, policy=engine)
    assert result.answer == "done"
    types = [e.type for e in store.read(session.session_id)]
    assert "policy_block" in types
    assert not (tmp_path / "evil.txt").exists()
    # denial visible to the model as the tool result
    results = [e.data.get("result", "") for e in store.read(session.session_id)
               if e.type == "tool_result"]
    assert any("Denied by policy" in r for r in results)
    store.close()


@pytest.mark.asyncio
async def test_loop_ask_auto_approves_and_logs(tmp_path):
    prov = FakeProvider([
        ModelResponse(text="", tool_calls=[ToolCall(
            name="bash", args={"cmd": "ver"})]),
        ModelResponse(text="done"),
    ])
    store = EventStore(tmp_path / "e.db")
    session = Session(source=tmp_path)
    session.open(base_dir=tmp_path / "ws")
    from lever.policy.engine import PolicyEngine as PE

    engine = PE([BashAllowlistRule(frozenset({"pytest"}))])  # ver not listed
    result = await run_loop(provider=prov, session=session, task="t",
                            config=HarnessConfig.b0(), store=store,
                            cache=None, policy=engine)
    assert result.answer == "done"
    evs = store.read(session.session_id)
    assert any(e.type == "approval_request" for e in evs)
    decisions = [e for e in evs if e.type == "approval_decision"]
    assert len(decisions) == 1 and decisions[0].data["allow"] is True
    assert decisions[0].data["by"] == "auto"
    store.close()


@pytest.mark.asyncio
async def test_loop_ask_custom_resolver_can_deny(tmp_path):
    async def nope(request):
        return False

    prov = FakeProvider([
        ModelResponse(text="", tool_calls=[ToolCall(
            name="bash", args={"cmd": "ver"})]),
        ModelResponse(text="done"),
    ])
    store = EventStore(tmp_path / "e.db")
    session = Session(source=tmp_path)
    session.open(base_dir=tmp_path / "ws")
    from lever.policy.engine import PolicyEngine as PE

    engine = PE([BashAllowlistRule(frozenset({"pytest"}))])
    result = await run_loop(provider=prov, session=session, task="t",
                            config=HarnessConfig.b0(), store=store,
                            cache=None, policy=engine, approve=nope)
    decisions = [e for e in store.read(session.session_id)
                 if e.type == "approval_decision"]
    assert decisions[0].data == {"name": "bash", "allow": False, "by": "human"}
    assert result.answer == "done"
    store.close()
