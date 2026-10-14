import json
import sys
from types import SimpleNamespace

sys.path.insert(0, "src")

import pytest

from lever.providers.base import ModelResponse
from lever.providers.fake import FakeProvider


@pytest.mark.asyncio
async def test_fake_provider_order():
    p = FakeProvider([ModelResponse(text="first"), ModelResponse(text="second")])
    r1 = await p.generate([{"role": "user", "content": "x"}], [], None)
    r2 = await p.generate([{"role": "user", "content": "x"}], [], None)
    assert (r1.text, r2.text) == ("first", "second")
    assert p.count_tokens([{"role": "user", "content": "hello"}]) >= 1


@pytest.mark.asyncio
async def test_gemini_history_conversion_without_api_key():
    # Conversion helpers must not require network/key.
    import os

    os.environ.pop("GEMINI_API_KEY", None)
    from lever.providers.gemini import GeminiProvider

    # Bypass __init__ (needs key) to test pure conversion logic.
    prov = GeminiProvider.__new__(GeminiProvider)
    from lever.providers.gemini import _extract_system

    messages = [
        {"role": "system", "content": "be brief"},
        {"role": "user", "content": "say hi"},
        {"role": "assistant", "content": "",
         "tool_calls": [{"name": "bash", "args": {"cmd": "echo hi"}}]},
        {"role": "tool", "name": "bash", "content": "hi"},
    ]
    assert _extract_system(messages) == "be brief"
    contents = prov._to_contents(messages)
    # System is SKIPPED here (sent as native system_instruction instead).
    assert all(t["role"] != "system" for t in contents)
    assert contents[0]["role"] == "user"
    assert contents[0]["parts"][0].text == "say hi"
    # Assistant turn renders a NATIVE function call (not "[calls: ...]" prose).
    call_part = contents[1]["parts"][0]
    assert call_part.function_call.name == "bash"
    assert dict(call_part.function_call.args) == {"cmd": "echo hi"}
    # Thought signatures echo verbatim when present, never invented.
    assert call_part.thought_signature in (None, "")
    from lever.providers.gemini import _decode_signature, _encode_signature

    assert _decode_signature(_encode_signature(b"A" * 224)) == b"A" * 224
    assert _encode_signature(None) is None and _decode_signature(None) is None
    assert _decode_signature("not-valid-base64!!!") is None
    sig_contents = prov._to_contents(
        [{"role": "assistant", "content": "",
          "tool_calls": [{"name": "bash", "args": {"cmd": "x"},
                          "thought_signature": _encode_signature(b"B" * 224)}]}]
    )
    assert sig_contents[0]["parts"][0].thought_signature == b"B" * 224
    # Thought blocks replay exactly (text may be None = signature-only block).
    tb_contents = prov._to_contents(
        [{"role": "assistant", "content": "",
          "thought_blocks": [{"text": None, "thought": True,
                              "thought_signature": _encode_signature(b"C" * 224)}]}]
    )
    tb_part = tb_contents[0]["parts"][0]
    assert tb_part.thought_signature == b"C" * 224
    assert tb_part.thought is True
    # Tool result renders a NATIVE function response (not "[tool result]" prose).
    assert contents[2]["role"] == "user"
    resp_part = contents[2]["parts"][0]
    assert resp_part.function_response.name == "bash"
    assert resp_part.function_response.response == {"result": "hi"}
    # No turn may contain the old prose annotations the model parroted live.
    for turn in contents:
        for part in turn["parts"]:
            text = getattr(part, "text", None)
            if isinstance(text, str):
                assert "[calls:" not in text and "[tool result" not in text


@pytest.mark.asyncio
async def test_from_response_keeps_signed_calls(tmp_path=None):
    """A functionCall WITH a signature must parse as a call (not vanish
    into thought_blocks). Regression: the thought-branch once diverted every
    signed call, so the model 'never called tools'."""
    from types import SimpleNamespace

    from lever.providers.gemini import (
        GeminiProvider,
        _decode_signature,
        _encode_signature,
    )

    prov = GeminiProvider.__new__(GeminiProvider)
    signed_call = SimpleNamespace(
        text=None,
        thought=None,
        thought_signature=b"S" * 8,
        function_call=SimpleNamespace(name="bash", args={"cmd": "x"}),
    )
    pure_sig = SimpleNamespace(
        text=None, thought=False, thought_signature=b"P" * 8, function_call=None
    )
    resp = SimpleNamespace(
        candidates=[SimpleNamespace(content=SimpleNamespace(
            parts=[signed_call, pure_sig]))],
        usage_metadata=None,
    )
    out = prov._from_response(resp)
    assert [c.name for c in out.tool_calls] == ["bash"]
    assert out.tool_calls[0].thought_signature == _encode_signature(b"S" * 8)
    assert _decode_signature(out.tool_calls[0].thought_signature) == b"S" * 8
    assert len(out.thought_blocks) == 1  # only the pure-signature part
    assert out.text == ""


@pytest.mark.asyncio
async def test_gemini_sends_system_instruction_natively(monkeypatch):
    from lever.providers.gemini import GeminiProvider

    calls = []
    provider = GeminiProvider.__new__(GeminiProvider)
    provider.model = "m"
    provider._client = SimpleNamespace(
        models=SimpleNamespace(
            generate_content=lambda **kwargs: (
                calls.append(kwargs) or SimpleNamespace(candidates=[], text="ok")
            )
        )
    )
    monkeypatch.setattr(provider, "_to_tools", lambda tools: [])

    await provider.generate(
        [{"role": "system", "content": "be brief"}, {"role": "user", "content": "hi"}],
        [],
        SimpleNamespace(temperature=0.2),
    )

    assert calls[0]["config"]["system_instruction"] == "be brief"
    assert all(t["role"] != "system" for t in calls[0]["contents"])


@pytest.mark.asyncio
async def test_gemini_generation_uses_environment_selected_model(monkeypatch):
    from lever.providers.gemini import GeminiProvider

    calls = []
    provider = GeminiProvider.__new__(GeminiProvider)
    provider.model = "model-from-env"
    provider._client = SimpleNamespace(
        models=SimpleNamespace(
            generate_content=lambda **kwargs: (
                calls.append(kwargs) or SimpleNamespace(candidates=[], text="ok")
            )
        )
    )
    monkeypatch.setattr(provider, "_to_tools", lambda tools: [])

    response = await provider.generate(
        [{"role": "user", "content": "hello"}],
        [],
        SimpleNamespace(model="config-override", temperature=0.2),
    )

    assert response.text == "ok"
    assert calls[0]["model"] == "model-from-env"


def _mock_local(payload: dict, seen: list) -> object:
    import httpx

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content.decode()))
        return httpx.Response(200, json=payload)

    return httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://test")


@pytest.mark.asyncio
async def test_local_provider_tool_call_round_trip():
    from lever.providers.local import LocalProvider, _to_openai

    seen: list = []
    payload = {
        "choices": [{"message": {
            "content": "",
            "tool_calls": [{"id": "call_1", "type": "function",
                            "function": {"name": "read_file",
                                         "arguments": '{"path": "a.py"}'}}]}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    }
    prov = LocalProvider(base_url="http://test", model="m",
                         client=_mock_local(payload, seen))
    resp = await prov.generate(
        [{"role": "user", "content": "read a.py"}],
        [{"name": "read_file", "description": "r",
          "parameters": {"type": "object",
                         "properties": {"path": {"type": "string"}},
                         "required": ["path"]}}],
        SimpleNamespace(temperature=0.2),
    )
    assert [(c.name, c.args) for c in resp.tool_calls] == [
        ("read_file", {"path": "a.py"})]
    assert (resp.input_tokens, resp.output_tokens) == (10, 5)
    body = seen[0]
    assert body["model"] == "m" and body["temperature"] == 0.2
    assert "tools" not in body  # text channel only (Gemma template 400s)
    assert "read_file(path: string)" in body["messages"][0]["content"]
    assert "```tool_code" in body["messages"][0]["content"]
    # History pairing: assistant calls link positionally to tool results.
    msgs = _to_openai([
        {"role": "assistant", "content": "",
         "tool_calls": [{"name": "bash", "args": {"cmd": "a"}},
                        {"name": "bash", "args": {"cmd": "b"}}]},
        {"role": "tool", "name": "bash", "content": "out-a"},
        {"role": "tool", "name": "bash", "content": "out-b"},
    ])
    assert [t["id"] for t in msgs[0]["tool_calls"]] == ["call_1", "call_2"]
    assert [m["tool_call_id"] for m in msgs[1:]] == ["call_1", "call_2"]
    await prov.aclose()


def test_to_openai_folds_system_and_alternates():
    from lever.providers.local import _to_openai

    msgs = _to_openai([
        {"role": "system", "content": "Be helpful."},
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "",
         "tool_calls": [{"name": "bash", "args": {"cmd": "x"}}]},
        {"role": "tool", "name": "bash", "content": "out"},
    ])
    assert [m["role"] for m in msgs] == ["user", "assistant", "tool"]
    assert msgs[0]["content"].startswith("[system] Be helpful.")


@pytest.mark.asyncio
async def test_local_provider_helpful_error_when_server_down():
    import httpx

    from lever.providers.local import LocalProvider

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://test")
    prov = LocalProvider(base_url="http://test", model="m", client=client)
    with pytest.raises(ConnectionError, match="docs/local_model.md"):
        await prov.generate([{"role": "user", "content": "hi"}], [], None)
    await prov.aclose()


def _fence_tools():
    return [
        {"name": "read_file", "description": "r",
         "parameters": {"type": "object",
                        "properties": {"path": {"type": "string"}},
                        "required": ["path"]}},
        {"name": "bash", "description": "b",
         "parameters": {"type": "object",
                        "properties": {"cmd": {"type": "string"},
                                       "timeout": {"type": "integer"}},
                        "required": ["cmd"]}},
        {"name": "write_file", "description": "w",
         "parameters": {"type": "object",
                        "properties": {"path": {"type": "string"},
                                       "content": {"type": "string"}},
                        "required": ["path", "content"]}},
    ]

def test_parse_fences_single_positional():
    from lever.providers.local import _parse_fences

    calls = _parse_fences(
        'first do this:\n```tool_code\nread_file("total.py")\n```\nthen that.',
        _fence_tools(),
    )
    assert [(c.name, c.args) for c in calls] == [
        ("read_file", {"path": "total.py"})]


def test_parse_fences_json_object():
    from lever.providers.local import _parse_fences

    calls = _parse_fences(
        '```tool_code\nbash({"cmd": "echo hi"})\n```', _fence_tools())
    assert [(c.name, c.args) for c in calls] == [
        ("bash", {"cmd": "echo hi"})]


def test_parse_fences_strictness():
    from lever.providers.local import _parse_fences

    tools = _fence_tools()
    # unknown tool name -> ignored
    assert _parse_fences('```tool_code\nnope("x")\n```', tools) == []
    # kwarg style resolves
    assert [(c.name, c.args) for c in
            _parse_fences('```tool_code\nread_file(path="a.py")\n```', tools)] == [
        ("read_file", {"path": "a.py"})]
    # single quotes too (observed live)
    assert [(c.name, c.args) for c in
            _parse_fences("```tool_code\nread_file(path='a.py')\n```", tools)] == [
        ("read_file", {"path": "a.py"})]
    # multi-line arguments (write_file with embedded newlines, observed live)
    assert [(c.name, c.args) for c in
            _parse_fences("```tool_code\nwrite_file(path=\"a.py\", "
                          "content=\"x = 1\\nprint(x)\")\n```", tools)] == [
        ("write_file", {"path": "a.py", "content": "x = 1\nprint(x)"})]
    # garbage stays prose
    assert _parse_fences('```tool_code\nread_file((()))\n```', tools) == []
    # no fence -> no calls (never hallucinate from prose)
    assert _parse_fences('please read_file("total.py") now', tools) == []
    # native calls win; fences only parse when native absent (in _from_openai)


def test_parse_fences_bare_form():
    from lever.providers.local import _parse_fences

    tools = _fence_tools()
    assert [(c.name, c.args) for c in
            _parse_fences('```tool_code\nread_file total.py\n```', tools)] == [
        ("read_file", {"path": "total.py"})]
    assert [(c.name, c.args) for c in
            _parse_fences('```tool_code\nbash echo hi\n```', tools)] == [
        ("bash", {"cmd": "echo hi"})]
    # bare form with braces still rejected
    assert _parse_fences('```tool_code\nbash {x}\n```', tools) == []
    # colon kwargs (Gemma English style) resolve against known properties
    assert [(c.name, c.args) for c in
            _parse_fences('```tool_code\nread_file path: "a.py"\n```', tools)] == [
        ("read_file", {"path": "a.py"})]
    # unknown keys rejected (incl. Windows drive letters)
    assert [(c.name, c.args) for c in
            _parse_fences('```tool_code\nread_file C:\\a.py\n```', tools)] == [
        ("read_file", {"path": "C:\\a.py"})]


@pytest.mark.asyncio
async def test_local_provider_uses_fences_when_no_native_calls():
    from lever.providers.local import LocalProvider

    seen: list = []
    payload = {
        "choices": [{"message": {
            "content": '```tool_code\nread_file("a.py")\n```',
            "tool_calls": None}}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 5},
    }

    def handler(request):
        import httpx as _hx
        seen.append(True)
        return _hx.Response(200, json=payload)

    import httpx

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://test")
    prov = LocalProvider(base_url="http://test", model="m", client=client)
    resp = await prov.generate(
        [{"role": "user", "content": "read a.py"}], _fence_tools(), None)
    assert [(c.name, c.args) for c in resp.tool_calls] == [
        ("read_file", {"path": "a.py"})]
    await prov.aclose()
