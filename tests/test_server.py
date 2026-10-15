import asyncio
import sys

sys.path.insert(0, "src")

import pytest

from lever.providers.base import ModelResponse, ToolCall
from lever.providers.fake import FakeProvider
from lever.server.app import create_app


def _repo(tmp_path):
    (tmp_path / "calc.py").write_text("def add(a, b):\n    return a + b\n",
                                      encoding="utf-8")
    return tmp_path


async def _mk(tmp_path, **kw):
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=create_app(str(tmp_path / "sess.db"), **kw))
    return AsyncClient(transport=transport, base_url="http://test")


async def _wait_done(client, sid, timeout=30.0):
    start = asyncio.get_running_loop().time()
    while asyncio.get_running_loop().time() - start < timeout:
        s = (await client.get(f"/sessions/{sid}")).json()
        if s["status"] in ("done", "error"):
            return s
        await asyncio.sleep(0.2)
    raise TimeoutError(f"session {sid} stuck: {s}")


@pytest.mark.asyncio
async def test_lifecycle_run_and_replay(tmp_path):
    _repo(tmp_path)
    client = await _mk(tmp_path)
    assert (await client.get("/health")).json() == {"status": "ok"}
    created = (await client.post("/sessions", json={
        "repo": str(tmp_path), "task": "say hi", "provider": "fake"})).json()
    sid = created["id"]
    assert (await client.get("/sessions")).json()[0]["id"] == sid
    final = await _wait_done(client, sid)
    assert final["status"] == "done"
    evs = (await client.get(f"/sessions/{sid}/events")).json()
    types = [e["type"] for e in evs]
    assert types[0] == "user_message" and types[-1] == "session_end"
    tail = (await client.get(f"/sessions/{sid}/events",
                             params={"since_seq": 2})).json()
    assert all(e["seq"] >= 2 for e in tail) and len(tail) < len(types)
    # live stream carries the terminal event
    body = ""
    async with client.stream("GET", f"/sessions/{sid}/stream") as resp:
        async for chunk in resp.aiter_text():
            body += chunk
            if "session_end" in body:
                break
    assert "session_end" in body
    await client.aclose()


@pytest.mark.asyncio
async def test_messages_starts_idle_session(tmp_path):
    _repo(tmp_path)
    client = await _mk(tmp_path)
    sid = (await client.post("/sessions", json={"repo": str(tmp_path)})).json()["id"]
    assert (await client.get(f"/sessions/{sid}")).json()["status"] == "idle"
    await client.post(f"/sessions/{sid}/messages", json={"content": "say hi"})
    assert (await _wait_done(client, sid))["status"] == "done"
    # a finished session accepts a fresh run on new messages
    r = await client.post(f"/sessions/{sid}/messages", json={"content": "again"})
    assert r.status_code == 200
    assert (await _wait_done(client, sid))["status"] == "done"
    await client.aclose()


@pytest.mark.asyncio
async def test_approval_flow_end_to_end(tmp_path):
    _repo(tmp_path)

    def scripted():
        return (FakeProvider([
            ModelResponse(text="", tool_calls=[ToolCall(
                name="bash", args={"cmd": "curl http://example.com"})]),
            ModelResponse(text="done"),
        ]), "scripted")

    client = await _mk(tmp_path, providers={"scripted": scripted})
    sid = (await client.post("/sessions", json={
        "repo": str(tmp_path), "task": "fetch",
        "provider": "scripted"})).json()["id"]
    req_id = None
    start = asyncio.get_running_loop().time()
    while asyncio.get_running_loop().time() - start < 30:
        evs = (await client.get(f"/sessions/{sid}/events")).json()
        reqs = [e for e in evs if e["type"] == "approval_request"]
        if reqs:
            req_id = reqs[0]["data"]["req_id"]
            break
        await asyncio.sleep(0.2)
    assert req_id, "no approval request surfaced"
    denied = (await client.post(f"/sessions/{sid}/approvals/{req_id}",
                                json={"allow": False})).json()
    assert denied == {"id": req_id, "allow": False}
    assert (await _wait_done(client, sid))["status"] == "done"
    evs = (await client.get(f"/sessions/{sid}/events")).json()
    dec = next(e for e in evs if e["type"] == "approval_decision")
    assert dec["data"] == {"req_id": req_id, "name": "bash",
                           "allow": False, "by": "human"}
    denied_results = [e for e in evs if e["type"] == "tool_result"]
    assert any("Denied by policy" in e["data"]["result"] for e in denied_results)
    # unknown approval id 404s
    r = await client.post(f"/sessions/{sid}/approvals/nope",
                          json={"allow": True})
    assert r.status_code == 404
    await client.aclose()


@pytest.mark.asyncio
async def test_fork_copies_prefix(tmp_path):
    _repo(tmp_path)
    client = await _mk(tmp_path)
    sid = (await client.post("/sessions", json={
        "repo": str(tmp_path), "task": "say hi", "provider": "fake"})).json()["id"]
    await _wait_done(client, sid)
    full = (await client.get(f"/sessions/{sid}/events")).json()
    child = (await client.post(f"/sessions/{sid}/fork",
                               params={"at_seq": 0})).json()["id"]
    assert child != sid
    child_evs = (await client.get(f"/sessions/{child}/events")).json()
    assert len(child_evs) == 1 and child_evs[0]["type"] == "user_message"
    assert [e["type"] for e in child_evs] == [e["type"] for e in full[:1]]
    # forked workspace opens lazily on first run, not at fork time
    assert (await client.get(f"/sessions/{child}/diff")).status_code == 404
    await client.aclose()


@pytest.mark.asyncio
async def test_providers_catalog(tmp_path):
    client = await _mk(tmp_path)
    provs = {p["id"]: p for p in (await client.get("/providers")).json()}
    assert set(provs) == {"auto", "fake", "local", "gemini"}
    assert provs["fake"]["configured"] is True
    await client.aclose()

@pytest.mark.asyncio
async def test_files_tree_content_and_diff(tmp_path):
    _repo(tmp_path)
    client = await _mk(tmp_path)
    sid = (await client.post("/sessions", json={"repo": str(tmp_path)})).json()["id"]
    await client.post(f"/sessions/{sid}/messages", json={"content": "say hi"})
    await _wait_done(client, sid)
    tree = await client.get(f"/sessions/{sid}/files")
    paths = [e["path"] for e in tree.json()]
    assert "calc.py" in paths
    assert all(not p.startswith(".git") for p in paths)
    file = (await client.get(f"/sessions/{sid}/file", params={"path": "calc.py"})).json()
    assert "def add" in file["content"] and file["truncated"] is False
    assert (await client.get(f"/sessions/{sid}/file",
                             params={"path": "../evil"})).status_code in (400, 404)
    fd = (await client.get(f"/sessions/{sid}/file-diff",
                           params={"path": "calc.py"})).json()
    # untouched file (modulo Windows CRLF normalization in git)
    assert fd["original"].splitlines() == fd["modified"].splitlines()
    await client.aclose()


@pytest.mark.asyncio
async def test_messages_with_attached_files(tmp_path):
    _repo(tmp_path)
    client = await _mk(tmp_path)
    sid = (await client.post("/sessions", json={"repo": str(tmp_path)})).json()["id"]
    await client.post(f"/sessions/{sid}/messages",
                      json={"content": "Say hi.", "files": ["calc.py"]})
    await _wait_done(client, sid)
    evs = (await client.get(f"/sessions/{sid}/events")).json()
    first = next(e for e in evs if e["type"] == "user_message")
    assert "=== calc.py ===" in first["data"]["content"]
    assert "def add" in first["data"]["content"]
    await client.aclose()


@pytest.mark.asyncio
async def test_create_model_override_recorded(tmp_path):
    _repo(tmp_path)
    client = await _mk(tmp_path)
    created = (await client.post("/sessions", json={
        "repo": str(tmp_path), "task": "say hi", "provider": "fake",
        "model": "custom-model"})).json()
    assert created["model"] == "custom-model"  # requested override echoed
    await _wait_done(client, created["id"])
    assert (await client.get(f"/sessions/{created['id']}")).json()["model"] == "fake"
    await client.aclose()


@pytest.mark.asyncio
async def test_file_diff_shows_modification(tmp_path):
    _repo(tmp_path)
    client = await _mk(tmp_path)
    sid = (await client.post("/sessions", json={"repo": str(tmp_path)})).json()["id"]
    await client.post(f"/sessions/{sid}/messages", json={"content": "say hi"})
    await _wait_done(client, sid)
    ws = (await client.get(f"/sessions/{sid}/files")).json()
    assert any(e["path"] == "calc.py" for e in ws if e["type"] == "file")
    await client.aclose()
