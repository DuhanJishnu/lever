"""Scripted fake provider for deterministic, free tests."""

from __future__ import annotations

from typing import Any

from .base import ModelResponse, ToolCall


class FakeProvider:
    """Returns scripted responses in order; records calls for assertions."""

    def __init__(self, script: list[ModelResponse] | None = None) -> None:
        self.script: list[ModelResponse] = script or [
            ModelResponse(text="hi", tool_calls=[])
        ]
        self.calls: list[dict[str, Any]] = []
        self._idx = 0

    async def generate(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        config: Any = None,
    ) -> ModelResponse:
        self.calls.append({"messages": messages, "tools": tools})
        resp = self.script[min(self._idx, len(self.script) - 1)]
        self._idx += 1
        return resp

    def count_tokens(self, messages: list[dict[str, Any]]) -> int:
        # Crude but deterministic: ~4 chars per token.
        total_chars = sum(len(str(m)) for m in messages)
        return max(1, total_chars // 4)

    @staticmethod
    def say_hi() -> FakeProvider:
        return FakeProvider([ModelResponse(text="hi")])


def tool_call_provider(calls: list[ToolCall], final_text: str = "done") -> FakeProvider:
    return FakeProvider(
        [ModelResponse(text="", tool_calls=calls), ModelResponse(text=final_text)]
    )
