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
            "messages": _to_openai(_with_tool_doc(messages, tools)),
            "temperature": float(getattr(config, "temperature", 0.2) or 0.2),
        }
        seed = getattr(config, "seed", None)
        if isinstance(seed, int) and seed >= 0:
            body["seed"] = seed
        # NOTE: no `tools` array is sent. llama.cpp's Gemma template cannot
        # build its tool-call parser for our histories (intermittent 400s:
        # "Conversation roles must alternate..."), and small models ignore
        # native schemas anyway. Tools travel as text; calls come back as
        # ```tool_code fences parsed by _parse_fences.
        try:
            resp = await self._http.post("/chat/completions", json=body)
            resp.raise_for_status()
        except httpx.ConnectError as e:
            raise ConnectionError(
                f"Cannot reach local model at {self.base_url} ({e}). "
                f"Start it first — see docs/local_model.md."
            ) from e
        return _from_openai(resp.json(), tools)

    async def aclose(self) -> None:
        await self._http.aclose()


def _to_openai(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Canonical history -> OpenAI messages. Assistant calls get synthetic ids
    (call_1, call_2, ...) paired positionally with following tool messages —
    valid because the loop strictly alternates calls then results.

    System messages are FOLDED into the next user turn ("[system] ...").
    Gemma's Jinja template requires strict user/assistant alternation and its
    tool-parser generation 400s on non-alternating histories; a standalone
    system turn is the known trigger.
    """
    out: list[dict[str, Any]] = []
    pending: list[str] = []
    call_idx = 0
    sys_prefix = ""
    for m in messages:
        role = m.get("role", "user")
        if role == "system":
            sys_prefix += "[system] " + str(m.get("content", "")) + "\n\n"
            pending = []
        elif role == "user":
            content = sys_prefix + str(m.get("content", ""))
            sys_prefix = ""
            out.append({"role": "user", "content": content})
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
    if sys_prefix:
        out.append({"role": "user", "content": sys_prefix})
    return out


def _from_openai(data: dict[str, Any], tools: list[dict[str, Any]]) -> ModelResponse:
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
    text = str(msg.get("content") or "")
    if not calls:
        # Small models often ignore the native schema and improvise fenced
        # calls (Gemma: ```tool_code NAME(...) ```). Meet them where they are.
        calls = _parse_fences(text, tools)
    usage = data.get("usage", {}) or {}
    return ModelResponse(
        text=text,
        tool_calls=calls,
        input_tokens=int(usage.get("prompt_tokens", 0) or 0),
        output_tokens=int(usage.get("completion_tokens", 0) or 0),
    )


def _tool_doc(tools: list[dict[str, Any]]) -> str:
    """Compact textual tool reference (the local model's only tool channel)."""
    lines = [
        "Available tools. To call one, emit a fenced block, exactly:",
        "```tool_code",
        'NAME({"arg": "value"})',
        "```",
        "One call per block; multiple blocks allowed. Known tools:",
    ]
    for t in tools:
        if not isinstance(t, dict) or "name" not in t:
            continue
        params = t.get("parameters", {}) or {}
        props = params.get("properties", {}) or {}
        required = params.get("required", []) or []
        sig = ", ".join(
            f"{p}: {props[p].get('type', '?')}"
            if isinstance(props.get(p), dict) else f"{p}: ?"
            for p in required
        )
        lines.append(f"- {t['name']}({sig}): {t.get('description', '')}")
    return "\n".join(lines)


def _with_tool_doc(
    messages: list[dict[str, Any]], tools: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    if not tools:
        return messages
    doc = _tool_doc(tools)
    msgs = [dict(m) for m in messages]
    for m in msgs:
        if m.get("role") in ("system", "user"):
            m["content"] = str(m.get("content", "")) + "\n\n" + doc
            return msgs
    return msgs + [{"role": "user", "content": doc}]


def _tool_index(tools: list[dict[str, Any]]) -> dict[str, str | None]:
    """name -> first required string param (for single-positional-arg fences)."""
    return {name: first for name, (first, _props) in _tool_schemas(tools).items()}


def _tool_schemas(
    tools: list[dict[str, Any]],
) -> dict[str, tuple[str | None, set[str]]]:
    """name -> (first required string param, known property names)."""
    out: dict[str, tuple[str | None, set[str]]] = {}
    for t in tools:
        if not isinstance(t, dict) or "name" not in t:
            continue
        params = t.get("parameters", {}) or {}
        required = params.get("required", []) or []
        props = params.get("properties", {}) or {}
        prop_names = {k for k in props if isinstance(k, str)}
        first = next(
            (p for p in required
             if isinstance(props.get(p), dict)
             and props[p].get("type") == "string"),
            None,
        )
        out[t["name"]] = (first, prop_names)
    return out


def _parse_fences(text: str, tools: list[dict[str, Any]]) -> list[ToolCall]:
    """Parse ```tool_code ... ``` blocks. Accepted call shapes (strict):

    - NAME("single string") / NAME({"k": "v"})   (parenthesized)
    - NAME bare rest-of-line                     (Gemma style: NAME total.py)
      -> single positional mapped to the tool's first required string param
    - anything else -> block ignored (stays prose, loop will stop)

    Strict by design: unknown names and unresolvable args never become calls.
    """
    import re

    index = _tool_index(tools)
    schemas = _tool_schemas(tools)
    calls: list[ToolCall] = []
    for body in re.findall(r"```tool_code\s*\n(.*?)```", text, re.DOTALL):
        body = body.strip()
        if not body:
            continue
        # Whole block first: calls whose arguments span lines (common for
        # write_file/edit_file with embedded newlines).
        name, args = _parse_call_line(body, index, schemas)
        if name is not None and args is not None:
            calls.append(ToolCall(name=name, args=args))
            continue
        for line in body.splitlines():
            line = line.strip()
            if not line:
                continue
            name, args = _parse_call_line(line, index, schemas)
            if name is not None and args is not None:
                calls.append(ToolCall(name=name, args=args))
    return calls


def _parse_call_line(
    line: str, index: dict[str, str | None],
    schemas: dict[str, tuple[str | None, set[str]]],
) -> tuple[str | None, dict[str, Any] | None]:
    import re

    m = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)\((.*)\)\s*", line, re.DOTALL)
    if m:
        name, raw = m.group(1), m.group(2).strip()
        if name not in index:
            return None, None
        if raw.startswith("{"):
            try:
                obj = json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                return None, None
            if isinstance(obj, dict):
                return name, {k: v for k, v in obj.items()}
            return None, None
        kw = _parse_kwargs(raw, schemas.get(name, (None, set()))[1])
        if kw is not None:
            return name, kw
        return name, _single_arg(index[name], raw)
    m = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)\s+(.+?)\s*", line, re.DOTALL)
    if m and m.group(1) in index:
        name = m.group(1)
        kw = _parse_kwargs(m.group(2), schemas.get(name, (None, set()))[1])
        if kw is not None:
            return name, kw
        return name, _single_arg(index[name], m.group(2))
    return None, None


def _parse_kwargs(raw: str, known: set[str]) -> dict[str, Any] | None:
    """Python/English-kwarg style: path="x", timeout=30 / path: "x".
    Keys must ALL be known schema properties (rejects Windows paths like
    C:\\a.py whose drive letter would parse as a key). Whole string must be
    consumed; values quoted or bare single tokens."""
    import re

    for sep in ("=", ":"):
        pairs = re.findall(
            r"([A-Za-z_][A-Za-z0-9_]*)\s*" + re.escape(sep) +
            r"\s*(\"[^\"]*\"|'[^']*'|[^\s,]+)"
            r"\s*(?:,|$)", raw)
        if not pairs:
            continue
        check = re.sub(
            r"[A-Za-z_][A-Za-z0-9_]*\s*" + re.escape(sep) +
            r"\s*(\"[^\"]*\"|'[^']*'|[^\s,]+)"
            r"\s*(?:,|$)", "", raw).strip()
        if check or any(k not in known for k, _ in pairs):
            continue
        args: dict[str, Any] = {}
        for k, v in pairs:
            if v.startswith('"'):
                try:
                    args[k] = json.loads(v)
                except (json.JSONDecodeError, ValueError):
                    break
            elif v.startswith("'"):
                args[k] = _unescape(v[1:-1])
            else:
                try:
                    args[k] = int(v)
                except ValueError:
                    args[k] = v
        else:
            return args
    return None


_SIMPLE_ESCAPES = {
    "n": "\n", "t": "\t", "r": "\r", "\\": "\\",
    "'": "'", '"': '"', "0": "\0",
}


def _unescape(s: str) -> str:
    """Decode standard escapes in single-quoted fence values — same semantics
    as the double-quoted (JSON) form, so both quote styles behave identically.
    Unknown escapes stay literal (safe for paths like C:\\q)."""
    import re

    return re.sub(
        r"\\(.)",
        lambda m: _SIMPLE_ESCAPES.get(m.group(1), m.group(0)),
        s,
    )


def _single_arg(first: str | None, raw: str) -> dict[str, Any] | None:
    import re

    if first is None:
        return None
    raw = raw.strip()
    q = re.fullmatch(r'"((?:[^"\\]|\\.)*)"', raw)
    if q is not None:
        try:
            return {first: json.loads(f'"{q.group(1)}"')}
        except (json.JSONDecodeError, ValueError):
            return None
    if raw and not any(c in raw for c in "{}()"):
        return {first: raw}
    return None
