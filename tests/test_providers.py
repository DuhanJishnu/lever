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
