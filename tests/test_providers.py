import sys

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
    contents = prov._to_contents(
        [
            {"role": "system", "content": "be brief"},
            {"role": "user", "content": "say hi"},
            {"role": "tool", "name": "read_file", "content": "hello"},
        ]
    )
    assert contents[0]["role"] == "user"
    assert "be brief" in contents[0]["parts"][0]["text"]
    assert contents[2]["role"] == "user"
