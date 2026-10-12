"""Provider protocol + shared response types."""

from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel


class ToolCall(BaseModel):
    name: str
    args: dict[str, Any] = {}
    call_id: str | None = None
    # Gemini 3.x thought signature: opaque bytes the model returns with each
    # function call and REQUIRES echoed back on replay (400 otherwise).
    # Stored base64-encoded so history stays JSON-serializable (events, cache).
    thought_signature: str | None = None


class ModelResponse(BaseModel):
    text: str = ""
    tool_calls: list[ToolCall] = []
    input_tokens: int = 0
    output_tokens: int = 0
    raw: dict[str, Any] = {}
    # Opaque thought blocks (text + signature) to replay EXACTLY. The docs
    # require resending all thought blocks unmodified for reasoning continuity;
    # the signature often lives here rather than on the functionCall part.
    thought_blocks: list[dict[str, Any]] = []


class Provider(Protocol):
    async def generate(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        config: Any,  # HarnessConfig (Any to avoid circular import)
    ) -> ModelResponse: ...

    def count_tokens(self, messages: list[dict[str, Any]]) -> int: ...
