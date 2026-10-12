"""B0 agent loop: deliberately naive. Fresh context, trace, stopped_by.

Lifecycle (harness owns it): session.open → create_tools(session) →
fresh context → guarded loop → session_end event → session.close (finally).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from .config import HarnessConfig
from .events import Event
from .guards import LoopState, compose_guards, max_steps_guard
from .session import Session

SYSTEM_B0 = (
    "You are a coding agent in a workspace. Use the available tools "
    "(read_file, grep, edit_file, write_file, bash) to complete the task. "
    "When the task is done, answer with a short summary and call no tools."
)


def fresh_context(task: str) -> list[dict[str, Any]]:
    """One isolated context per task — no history leaks between tasks."""
    return [
        {"role": "system", "content": SYSTEM_B0},
        {"role": "user", "content": task},
    ]


def estimate_tokens(messages: list[dict[str, Any]]) -> int:
    """Cheap local estimate (~4 chars/token) for per-iteration trace stats.
    Exact API counts are used only where needed (compaction, B5)."""
    return max(1, sum(len(str(m.get("content", ""))) for m in messages) // 4)


StoppedBy = Literal["model", "guardrail", "max_steps"]


@dataclass
class ToolEvent:
    tool: str
    args: dict[str, Any]
    result: str


@dataclass
class LoopIteration:
    index: int
    outcome: Literal["tool_calls", "answer"]
    tool_events: list[ToolEvent] = field(default_factory=list)
    context_size: int = 0


@dataclass
class LoopResult:
    answer: str
    iterations: int
    trace: list[LoopIteration] = field(default_factory=list)
    stopped_by: StoppedBy = "model"
    session_id: str = ""


async def run_loop(
    *,
    provider: Any,
    session: Session,
    task: str,
    config: HarnessConfig,
    store: Any,  # EventStore (Any to keep core import-light)
    cache: Any | None = None,  # ResponseCache — skips repeat API calls
    tools: Any | None = None,  # ToolRegistry — created from session if omitted
) -> LoopResult:
    from ..tools.registry import create_tools  # local import: tools depend on core, not vice versa

    workspace = session.workspace or session.open()
    if tools is None:
        tools = create_tools(workspace)
    guards = compose_guards(max_steps_guard)  # B0: max_steps only; B8 extends this list

    store.append(Event(session_id=session.session_id, seq=0,
                       type="user_message", data={"content": task}))
    messages = fresh_context(task)
    trace: list[LoopIteration] = []
    stopped_by: StoppedBy = "model"
    answer = ""

    try:
        for _ in range(config.max_steps):
            state = LoopState(
                iterations=len(trace),
                max_steps=config.max_steps,
                context_messages=len(messages),
                est_tokens=estimate_tokens(messages),
            )
            guard = guards(state)
            if guard.verdict == "stop":
                stopped_by = "guardrail" if "max_steps" not in guard.reason else "max_steps"
                break

            ctx_size = estimate_tokens(messages)
            store.append(Event(session_id=session.session_id, seq=0,
                               type="model_request",
                               data={"messages": messages, "model": config.model}))
            resp = await _generate(provider, messages, tools.definitions, config, cache)
            store.append(Event(session_id=session.session_id, seq=0,
                               type="model_response", data=resp.model_dump()
                               if hasattr(resp, "model_dump") else dict(resp)))
            text = str(getattr(resp, "text", ""))
            tool_calls = list(getattr(resp, "tool_calls", []) or [])

            if not tool_calls:
                answer = text or "(no response)"
                messages.append({"role": "assistant", "content": answer})
                trace.append(LoopIteration(index=len(trace) + 1,
                                           outcome="answer", context_size=ctx_size))
                stopped_by = "model"
                break

            # Record assistant turn incl. which calls it made (B0 simplification:
            # call IDs aren't replayed; the live-model test decides if this suffices).
            calls_note = ", ".join(
                f"{c.name}({c.args})" if hasattr(c, "name") else str(c)
                for c in tool_calls
            )
            messages.append({"role": "assistant",
                             "content": f"{text}\n[calls: {calls_note}]" if text
                             else f"[calls: {calls_note}]"})
            events: list[ToolEvent] = []
            for call in tool_calls:
                name = call.name if hasattr(call, "name") else call.get("name", "")
                cargs = call.args if hasattr(call, "args") else call.get("args", {})
                store.append(Event(session_id=session.session_id, seq=0,
                                   type="tool_call",
                                   data={"name": name, "args": cargs}))
                result = await tools.run(name, cargs)
                store.append(Event(session_id=session.session_id, seq=0,
                                   type="tool_result",
                                   data={"name": name, "result": result}))
                messages.append({"role": "tool", "name": name, "content": result})
                events.append(ToolEvent(tool=name, args=cargs, result=result))
            trace.append(LoopIteration(index=len(trace) + 1, outcome="tool_calls",
                                       tool_events=events, context_size=ctx_size))
        else:
            stopped_by = "max_steps"
    finally:
        session.close()

    result = LoopResult(answer=answer or "(stopped)",
                        iterations=len(trace), trace=trace,
                        stopped_by=stopped_by, session_id=session.session_id)
    store.append(Event(session_id=session.session_id, seq=0, type="session_end",
                       data={"stopped_by": stopped_by, "iterations": len(trace),
                             "answer": result.answer}))
    return result


async def _generate(
    provider: Any, messages: list[dict[str, Any]], definitions: list[dict[str, Any]],
    config: HarnessConfig, cache: Any | None,
) -> Any:
    if cache is None:
        return await provider.generate(messages, definitions, config)
    from ..providers.cache import cache_key

    key = cache_key(config.model, messages, definitions, config)
    hit = cache.get(key)
    if hit is not None:
        from ..providers.base import ModelResponse

        return ModelResponse(**hit)
    resp = await provider.generate(messages, definitions, config)
    cache.put(key, resp.model_dump() if hasattr(resp, "model_dump") else dict(resp))
    return resp
