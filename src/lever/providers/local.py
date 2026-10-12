"""Local provider: any OpenAI-compatible chat endpoint (llama-server, etc.).

Configure:
    LEVER_LOCAL_URL=http://localhost:8080/v1   # llama-server base URL
    LEVER_LOCAL_MODEL=gemma-3-4b               # model name served there
See docs/local_model.md for setup. No signatures, no server token counts:
`count_tokens` is a local chars//4 estimate (documented, constant).
"""

from __future__ import annotations

import json
import os
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from .base import ModelResponse, ToolCall


class LocalProvider:
    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout_s: float = 180.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        raw_url = base_url or os.getenv(
            "LEVER_LOCAL_URL", "http://localhost:8080/v1")
        self.base_url = (raw_url or "http://localhost:8080/v1").rstrip("/")
        self.model = model or os.getenv("LEVER_LOCAL_MODEL", "")
        if not self.model:
            raise ValueError("LEVER_LOCAL_MODEL is not set (see docs/local_model.md)")
        self._http = client or httpx.AsyncClient(
            base_url=self.base_url, timeout=timeout_s)

    def count_tokens(self, messages: list[dict[str, Any]]) -> int:
        return max(1, sum(len(str(m.get("content", ""))) for m in messages) // 4)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10),
           reraise=True)
    async def generate(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        config: Any = None,
    ) -> ModelResponse:
        body = {
            "model": self.model,
            "messages": _to_openai(messages),
            "temperature": float(getattr(config, "temperature", 0.2) or 0.2),
        }
        if tools:
            body["tools"] = [
                {"type": "function",
                 "function": {"name": t["name"],
                              "description": t.get("description", ""),
                              "parameters": t.get("parameters", {"type": "object"})}}
                for t in tools if isinstance(t, dict) and "name" in t
            ]
        try:
            resp = await self._http.post("/chat/completions", json=body)
            resp.raise_for_status()
        except httpx.ConnectError as e:
            raise ConnectionError(
                f"Cannot reach local model at {self.base_url} ({e}). "
                f"Start it first — see docs/local_model.md."
            ) from e
        return _from_openai(resp.json())

    async def aclose(self) -> None:
        await self._http.aclose()


def _to_openai(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Canonical history -> OpenAI messages. Assistant calls get synthetic ids
    (call_1, call_2, ...) paired positionally with following tool messages —
    valid because the loop strictly alternates calls then results."""
    out: list[dict[str, Any]] = []
    pending: list[str] = []
    call_idx = 0
    for m in messages:
        role = m.get("role", "user")
        if role == "system":
            out.append({"role": "system", "content": str(m.get("content", ""))})
            pending = []
        elif role == "user":
            out.append({"role": "user", "content": str(m.get("content", ""))})
            pending = []
        elif role in ("assistant", "model"):
            tcs = []
            for call in m.get("tool_calls") or []:
                call_idx += 1
                cid = f"call_{call_idx}"
                pending.append(cid)
                tcs.append({
                    "id": cid, "type": "function",
                    "function": {
                        "name": call.get("name", ""),
                        "arguments": json.dumps(call.get("args", {})),
                    },
                })
            msg: dict[str, Any] = {"role": "assistant",
                                   "content": str(m.get("content", "")) or None}
            if tcs:
                msg["tool_calls"] = tcs
            out.append(msg)
        elif role == "tool":
            cid = pending.pop(0) if pending else f"call_{call_idx + 1}"
            out.append({"role": "tool", "tool_call_id": cid,
                        "content": str(m.get("content", ""))})
        else:
            out.append({"role": "user", "content": str(m.get("content", ""))})
            pending = []
    return out


def _from_openai(data: dict[str, Any]) -> ModelResponse:
    try:
        msg = data["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as e:
        raise ValueError(f"Unexpected local-model response shape: {str(data)[:300]}") from e
    calls = []
    for tc in msg.get("tool_calls") or []:
        fn = tc.get("function", {}) if isinstance(tc, dict) else {}
        raw_args = fn.get("arguments", "{}") or "{}"
        try:
            args = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
        except (json.JSONDecodeError, TypeError, ValueError):
            args = {"_raw": str(raw_args)}
        calls.append(ToolCall(name=fn.get("name", ""),
                              args=args if isinstance(args, dict) else {"_raw": str(args)},
                              call_id=tc.get("id") if isinstance(tc, dict) else None))
    usage = data.get("usage", {}) or {}
    return ModelResponse(
        text=str(msg.get("content") or ""),
        tool_calls=calls,
        input_tokens=int(usage.get("prompt_tokens", 0) or 0),
        output_tokens=int(usage.get("completion_tokens", 0) or 0),
    )
