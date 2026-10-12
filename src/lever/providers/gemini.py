"""Gemini provider via google-genai SDK with retry + backoff.

Risk being retired here (plan Phase 0): multi-turn function calling —
how the SDK expects tool results replayed in history. This adapter keeps
history as plain dicts and converts at the call boundary, so quirks stay
in one file.
"""

from __future__ import annotations

import os
from typing import Any, cast

from tenacity import retry, stop_after_attempt, wait_exponential

from .base import ModelResponse, ToolCall


def _encode_signature(raw: Any) -> str | None:
    """Thought signatures arrive as bytes; store base64 so history,
    events, and cache stay JSON-serializable."""
    if raw is None:
        return None
    if isinstance(raw, bytes):
        import base64

        return base64.b64encode(raw).decode("ascii")
    return str(raw)


def _decode_signature(stored: Any) -> bytes | None:
    if not stored:
        return None
    if isinstance(stored, bytes):
        return stored
    import base64

    try:
        return base64.b64decode(str(stored))
    except Exception:
        return None


def _extract_system(messages: list[dict[str, Any]]) -> str | None:
    """First system message wins; the loop always sends exactly one."""
    for m in messages:
        if m.get("role") == "system" and str(m.get("content", "")):
            return str(m["content"])
    return None


class GeminiProvider:
    def __init__(self, api_key: str | None = None) -> None:
        self.model = os.getenv("LEVER_MODEL", "")
        if not self.model:
            raise ValueError("LEVER_MODEL is not set (see .env.example)")
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY is not set (see .env.example)")
        # Lazy import so tests without the SDK still collect.
        from google import genai

        self._client = genai.Client(api_key=self.api_key)

    def count_tokens(self, messages: list[dict[str, Any]]) -> int:
        try:
            resp = self._client.models.count_tokens(
                model=str(self.model),
                contents=cast(Any, self._to_contents(messages)),
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
        system_text = _extract_system(messages)

        # google-genai SDK is sync; run in thread to avoid blocking the loop.
        import asyncio

        def _call() -> Any:
            kwargs: dict[str, Any] = {
                "model": self.model,
                "contents": contents,
            }
            # Only pass generation config we are sure about.
            cfg: dict[str, Any] = {"temperature": temperature}
            if system_text:
                cfg["system_instruction"] = system_text
            kwargs["config"] = cfg
            if tool_config:
                tools_cfg = kwargs["config"]
                assert isinstance(tools_cfg, dict)
                tools_cfg["tools"] = tool_config
            return self._client.models.generate_content(**kwargs)

        resp = await asyncio.to_thread(_call)
        return self._from_response(resp)

    # ---- conversion helpers (the quirk-containment zone) ----

    def _to_contents(self, messages: list[dict[str, Any]]) -> list[Any]:
        """Render our plain dicts as native SDK parts.

        System messages are SKIPPED here — generate() sends them as native
        `system_instruction` instead (folding them into user turns confused
        tool elicitation). Assistant turns with `tool_calls` become model
        content with real FunctionCall parts; tool results become user content
        with real FunctionResponse parts. This pairing is what keeps multi-turn
        function calling alive — prose framings get parroted, parts get
        continued (proven by the failed-then-fixed live runs).
        """
        from google.genai import types

        out: list[Any] = []
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            if role == "system":
                continue
            elif role in ("user", "model", "assistant"):
                r = "model" if role in ("model", "assistant") else "user"
                parts: list[Any] = []
                if str(content):
                    parts.append(types.Part(text=str(content)))
                # Thought blocks replay EXACTLY and FIRST (reasoning continuity).
                for block in m.get("thought_blocks") or []:
                    sig = _decode_signature(block.get("thought_signature"))
                    parts.append(types.Part(
                        text=block.get("text"),
                        thought=bool(block.get("thought", True)),
                        thought_signature=sig,
                    ))
                if r == "model":
                    for call in m.get("tool_calls") or []:
                        fc_part = types.Part.from_function_call(
                            name=call.get("name", ""),
                            args=dict(call.get("args", {}) or {}),
                        )
                        # Echo the thought signature verbatim (Gemini 3.x 400s
                        # without it). Never invent one when absent.
                        sig = _decode_signature(call.get("thought_signature"))
                        if sig is not None:
                            fc_part.thought_signature = sig
                        parts.append(fc_part)
                out.append({"role": r, "parts": parts or [{"text": ""}]})
            elif role == "tool":
                out.append({
                    "role": "user",
                    "parts": [types.Part.from_function_response(
                        name=str(m.get("name", "")),
                        response={"result": str(content)},
                    )],
                })
            else:
                out.append({"role": "user", "parts": [{"text": str(content)}]})
        return out

    def _to_tools(self, tools: list[dict[str, Any]]) -> list[Any]:
        """Translate our canonical defs ({name, description, parameters}) into
        SDK Tool(function_declarations=[...]). Canonical form keeps us
        provider-agnostic: the same defs render as OpenAI-style functions for
        an OpenAI-compatible endpoint later."""
        from google.genai import types

        decls: list[Any] = []
        for t in tools:
            if isinstance(t, dict) and "name" in t:
                decls.append(
                    types.FunctionDeclaration(
                        name=t["name"],
                        description=t.get("description", ""),
                        parameters=t.get("parameters", {"type": "object"}),
                    )
                )
        return [types.Tool(function_declarations=decls)] if decls else []

    def _from_response(self, resp: Any) -> ModelResponse:
        text_parts: list[str] = []
        calls: list[ToolCall] = []
        thoughts: list[dict[str, Any]] = []
        try:
            for cand in getattr(resp, "candidates", []) or []:
                for part in getattr(getattr(cand, "content", None), "parts", []) or []:
                    sig = _encode_signature(
                        getattr(part, "thought_signature", None)
                    )
                    fc = getattr(part, "function_call", None)
                    if fc is not None:
                        # Function call: the signature rides ON the call part.
                        # (A signed call is NOT a standalone thought block —
                        # filing it as one drops the call entirely.)
                        calls.append(
                            ToolCall(
                                name=getattr(fc, "name", ""),
                                args=dict(getattr(fc, "args", {}) or {}),
                                thought_signature=sig,
                            )
                        )
                        continue
                    t = getattr(part, "text", None)
                    if sig and not t:
                        # Pure signature block (no text, no call): replay
                        # exactly or reasoning continuity breaks.
                        thoughts.append({
                            "text": None,
                            "thought": bool(getattr(part, "thought", None)),
                            "thought_signature": sig,
                        })
                        continue
                    if t:
                        text_parts.append(t)
                        if sig:
                            # Text carrying a signature: remember it for exact
                            # replay alongside the display text.
                            thoughts.append({
                                "text": t,
                                "thought": bool(getattr(part, "thought", None)),
                                "thought_signature": sig,
                            })
        except Exception:
            pass
        # Fallback: some SDK versions expose .text directly. Suppress the
        # "non-text parts" warning — we already walked parts above, and this
        # path only runs when no text parts were found (e.g. call-only turns).
        if not text_parts:
            try:
                import warnings

                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
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
            thought_blocks=thoughts,
        )
