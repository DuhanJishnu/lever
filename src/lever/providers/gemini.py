"""Gemini provider via google-genai SDK with retry + backoff.

Risk being retired here (plan Phase 0): multi-turn function calling —
how the SDK expects tool results replayed in history. This adapter keeps
history as plain dicts and converts at the call boundary, so quirks stay
in one file.
"""

from __future__ import annotations

import os
from typing import Any

from tenacity import retry, stop_after_attempt, wait_exponential

from .base import ModelResponse, ToolCall


class GeminiProvider:
    def __init__(self, model: str | None = None, api_key: str | None = None) -> None:
        self.model = model or os.getenv("LEVER_MODEL", "gemini-2.5-flash")
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY is not set (see .env.example)")
        # Lazy import so tests without the SDK still collect.
        from google import genai  # type: ignore[import-not-found]

        self._client = genai.Client(api_key=self.api_key)

    def count_tokens(self, messages: list[dict[str, Any]]) -> int:
        try:
            resp = self._client.models.count_tokens(
                model=self.model, contents=self._to_contents(messages)
            )
            return int(resp.total_tokens or 0)
        except Exception:
            # Offline fallback: ~4 chars/token.
            return max(1, sum(len(str(m)) for m in messages) // 4)

    @retry(stop=stop_after_attempt(5), wait=wait_exponential(min=2, max=30))
    async def generate(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        config: Any = None,
    ) -> ModelResponse:
        contents = self._to_contents(messages)
        tool_config = self._to_tools(tools)
        temperature = float(getattr(config, "temperature", 0.2) or 0.2)

        # google-genai SDK is sync; run in thread to avoid blocking the loop.
        import asyncio

        def _call() -> Any:
            kwargs: dict[str, Any] = {
                "model": getattr(config, "model", self.model) or self.model,
                "contents": contents,
            }
            # Only pass generation config we are sure about.
            kwargs["config"] = {"temperature": temperature}
            if tool_config:
                kwargs["config"]["tools"] = tool_config  # type: ignore[index]
            return self._client.models.generate_content(**kwargs)

        resp = await asyncio.to_thread(_call)
        return self._from_response(resp)

    # ---- conversion helpers (the quirk-containment zone) ----

    def _to_contents(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Accept our plain {role, content} dicts; pass through otherwise."""
        out: list[dict[str, Any]] = []
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            if role == "system":
                # google-genai prefers system_instruction; fold into user turn
                # to keep history replay simple and multi-turn safe.
                out.append({"role": "user", "parts": [{"text": f"[system] {content}"}]})
            elif role in ("user", "model", "assistant"):
                r = "model" if role in ("model", "assistant") else "user"
                out.append({"role": r, "parts": [{"text": str(content)}]})
            elif role == "tool":
                # Tool results: keep as user parts with explicit framing so the
                # model can continue multi-turn function calling.
                out.append(
                    {
                        "role": "user",
                        "parts": [
                            {
                                "text": (
                                    f"[tool result {m.get('name', '')}]: {content}"
                                )
                            }
                        ],
                    }
                )
            else:
                out.append({"role": "user", "parts": [{"text": str(content)}]})
        return out

    def _to_tools(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        # SDK accepts OpenAPI-style function_declarations; pass through.
        return tools

    def _from_response(self, resp: Any) -> ModelResponse:
        text_parts: list[str] = []
        calls: list[ToolCall] = []
        try:
            for cand in getattr(resp, "candidates", []) or []:
                for part in getattr(getattr(cand, "content", None), "parts", []) or []:
                    t = getattr(part, "text", None)
                    if t:
                        text_parts.append(t)
                    fc = getattr(part, "function_call", None)
                    if fc is not None:
                        calls.append(
                            ToolCall(
                                name=getattr(fc, "name", ""),
                                args=dict(getattr(fc, "args", {}) or {}),
                            )
                        )
        except Exception:
            pass
        # Fallback: some SDK versions expose .text directly.
        if not text_parts:
            try:
                t = getattr(resp, "text", "")
                if t:
                    text_parts.append(str(t))
            except Exception:
                pass
        usage = getattr(resp, "usage_metadata", None)
        return ModelResponse(
            text="".join(text_parts),
            tool_calls=calls,
            input_tokens=int(getattr(usage, "prompt_token_count", 0) or 0),
            output_tokens=int(getattr(usage, "candidates_token_count", 0) or 0),
        )
