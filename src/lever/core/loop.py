"""B0 agent loop: deliberately naive. Fresh context, trace, stopped_by.

Lifecycle (harness owns it): session.open → create_tools(session) →
fresh context → guarded loop → session_end event → session.close (finally).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from .config import HarnessConfig
from .events import Event
from .guards import (
    LoopState,
    RepeatTracker,
    call_key,
    compose_guards,
    is_failure,
    max_context_messages,
    max_steps_guard,
    max_tokens_guard,
    time_limit_guard,
)
from .session import Session
from .verify import VERIFY_MAX_ROUNDS, verify_completion

SYSTEM_B0 = (
    "You are a coding agent in a workspace. Use the available tools "
    "(read_file, grep, edit_file, write_file, bash) to complete the task. "
    "When the task is done, answer with a short summary and call no tools."
)

# Empty turns (no text, no calls) are transient model-side hiccups, not "done".
# Retry them within the step budget instead of stopping. Constant across all
# ablation configs, so it cannot bias B0-vs-B8 comparisons.
MAX_EMPTY_RETRIES = 3


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


def _mutated(events: list[ToolEvent]) -> bool:
    """Did any tool turn actually change a file? (edit applied / file wrote)."""
    for e in events:
        if e.tool == "edit_file" and "Edit applied" in e.result:
            return True
        if e.tool == "write_file" and e.result.startswith("Wrote "):
            return True
    return False


StoppedBy = Literal["model", "guardrail", "max_steps", "empty"]


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
    stop_reason: str = ""  # which guard fired / why (B8 analysis)


async def run_loop(
    *,
    provider: Any,
    session: Session,
    task: str,
    config: HarnessConfig,
    store: Any,  # EventStore (Any to keep core import-light)
    cache: Any | None = None,  # ResponseCache — skips repeat API calls
    tools: Any | None = None,  # ToolRegistry — created from session if omitted
    seed: int = 0,  # sampling seed: isolates cache entries per replicate
) -> LoopResult:
    import time as _time

    from ..tools.registry import create_tools  # local import: tools depend on core, not vice versa

    workspace = session.workspace or session.open()
    if tools is None:
        tools = create_tools(workspace, config)
    want_guard = bool(getattr(config, "loop_guard", False))
    if want_guard:
        guards = compose_guards(
            max_steps_guard,
            max_context_messages(),
            max_tokens_guard(config.context_budget_tokens),
            time_limit_guard(),
        )
        tracker = RepeatTracker()
    else:
        guards = compose_guards(max_steps_guard)  # B0: max_steps only
        tracker = None

    store.append(Event(session_id=session.session_id, seq=0,
                       type="user_message", data={"content": task}))
    messages = fresh_context(task)
    want_map = bool(getattr(config, "repo_map", False))
    want_mask = bool(getattr(config, "observation_masking", False))
    want_compact = bool(getattr(config, "compaction", False))
    want_verify = bool(getattr(config, "verify_loop", False))
    verify_rounds = 0
    touched: set[str] = set()
    if want_map:
        from ..context.repomap import build_repomap

        messages[0]["content"] += ("\n\n# Repository map (pinned):\n"
                                   + build_repomap(workspace, task))
    trace: list[LoopIteration] = []
    stopped_by: StoppedBy = "model"
    stop_reason = ""
    answer = ""
    empty_retries = 0
    history: list[str] = []
    t0 = _time.monotonic()

    try:
        for _ in range(config.max_steps):
            state = LoopState(
                iterations=len(trace),
                max_steps=config.max_steps,
                context_messages=len(messages),
                est_tokens=estimate_tokens(messages),
                elapsed_s=_time.monotonic() - t0,
                history=tuple(history),
            )
            guard = guards(state)
            if guard.verdict == "stop":
                stop_reason = guard.reason
                stopped_by = "guardrail" if "max_steps" not in guard.reason else "max_steps"
                break

            if want_compact:
                from ..context.compaction import compact_history, needs_compaction

                budget = int(config.context_budget_tokens or 0)
                if needs_compaction(estimate_tokens(messages), budget):
                    messages, info = await compact_history(
                        messages, provider, config)
                    if info is not None:
                        store.append(Event(
                            session_id=session.session_id, seq=0,
                            type="context_compacted", data=info))

            ctx_size = estimate_tokens(messages)
            model_name = str(getattr(provider, "model", "fake"))
            store.append(Event(session_id=session.session_id, seq=0,
                               type="model_request",
                               data={"messages": messages, "model": model_name}))
            if want_mask:
                from ..context.masking import mask_observations

                send_messages, _n_masked = mask_observations(messages)
            else:
                send_messages = messages
            resp = await _generate(provider, send_messages, tools.definitions, config, cache, seed)
            store.append(Event(session_id=session.session_id, seq=0,
                               type="model_response", data=resp.model_dump()
                               if hasattr(resp, "model_dump") else dict(resp)))
            text = str(getattr(resp, "text", ""))
            tool_calls = list(getattr(resp, "tool_calls", []) or [])
            thought_blocks = list(getattr(resp, "thought_blocks", []) or [])

            if not text and not tool_calls:
                # Transient empty turn: do NOT log it as an answer and do NOT
                # append it to history (it would pollute replay). Retry.
                empty_retries += 1
                if empty_retries > MAX_EMPTY_RETRIES:
                    answer = "(no response)"
                    stopped_by = "empty"
                    break
                continue
            empty_retries = 0

            if not tool_calls:
                answer = text or "(no response)"
                if want_verify and verify_rounds < VERIFY_MAX_ROUNDS:
                    # Model claims done: check it against visible tests before
                    # believing it. Failure -> trimmed report, model continues.
                    verify_rounds += 1
                    vr = await verify_completion(workspace, answer, trace)
                    store.append(Event(
                        session_id=session.session_id, seq=0, type="tool_call",
                        data={"name": "verify_tests",
                              "args": {"cmd": vr.command}}))
                    store.append(Event(
                        session_id=session.session_id, seq=0, type="tool_result",
                        data={"name": "verify_tests",
                              "result": ("verify: PASS. " if vr.passed else
                                         "verify: FAIL. ") + vr.report[:2000]}))
                    if vr.passed:
                        messages.append({"role": "assistant", "content": answer})
                        trace.append(LoopIteration(
                            index=len(trace) + 1, outcome="answer",
                            context_size=ctx_size))
                        stopped_by = "model"
                        break
                    if verify_rounds >= VERIFY_MAX_ROUNDS:
                        answer = answer + " [unverified: tests still failing]"
                        messages.append({"role": "assistant", "content": answer})
                        trace.append(LoopIteration(
                            index=len(trace) + 1, outcome="answer",
                            context_size=ctx_size))
                        stopped_by = "model"
                        break
                    messages.append({"role": "assistant", "content": answer})
                    messages.append({"role": "user", "content":
                        "[verify] Your 'done' does not hold:\n" + vr.report[:2000] +
                        "\nKeep working. Run the tests yourself when you think "
                        "it is fixed."})
                    continue
                messages.append({"role": "assistant", "content": answer})
                trace.append(LoopIteration(index=len(trace) + 1,
                                           outcome="answer", context_size=ctx_size))
                stopped_by = "model"
                break

            # Record the assistant turn with STRUCTURED tool calls (not prose).
            # The provider renders these as native function-call parts, so the
            # model sees its own calls as calls — prose annotations here get
            # parroted back as final answers (observed live with 3.8-flash).
            def _as_dict(call: Any) -> dict[str, Any]:
                if hasattr(call, "model_dump"):
                    d = call.model_dump()
                    return {"name": d.get("name", ""), "args": d.get("args", {}),
                            "thought_signature": d.get("thought_signature")}
                return {"name": call.get("name", ""), "args": call.get("args", {}),
                        "thought_signature": call.get("thought_signature")}

            assistant_msg: dict[str, Any] = {"role": "assistant", "content": text}
            assistant_msg["tool_calls"] = [_as_dict(c) for c in tool_calls]
            assistant_msg["thought_blocks"] = thought_blocks
            messages.append(assistant_msg)
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
            if want_guard and tracker is not None:
                keys = [call_key(e.tool, e.args) for e in events]
                history.extend(keys)
                all_failed = bool(events) and all(
                    is_failure(e.result) for e in events)
                action, intervention = tracker.update(keys, all_failed)
                if action in ("nudge", "replan"):
                    store.append(Event(
                        session_id=session.session_id, seq=0,
                        type="harness_nudge",
                        data={"kind": action, "text": intervention,
                              "triggers": tracker.triggers}))
                    messages.append({"role": "user", "content": intervention})
                elif action == "stop":
                    stop_reason = intervention
                    stopped_by = "guardrail"
                    store.append(Event(
                        session_id=session.session_id, seq=0,
                        type="harness_nudge",
                        data={"kind": "stop", "text": intervention,
                              "triggers": tracker.triggers}))
                    trace.append(LoopIteration(
                        index=len(trace) + 1, outcome="tool_calls",
                        tool_events=events, context_size=ctx_size))
                    break
            if want_map and _mutated(events):
                # A file changed: refresh the pinned map so later turns see
                # new/moved definitions. Cheap on small repos; rebuilds only.
                from ..context.repomap import build_repomap

                touched.update(
                    str(e.args.get("path", "")) for e in events
                    if e.tool in ("edit_file", "write_file") and e.args.get("path"))
                messages[0]["content"] = (
                    SYSTEM_B0 + "\n\n# Repository map (pinned):\n"
                    + build_repomap(workspace, task, touched))
            trace.append(LoopIteration(index=len(trace) + 1, outcome="tool_calls",
                                       tool_events=events, context_size=ctx_size))
        else:
            stopped_by = "max_steps"
    finally:
        session.close()

    result = LoopResult(answer=answer or "(stopped)",
                        iterations=len(trace), trace=trace,
                        stopped_by=stopped_by, session_id=session.session_id,
                        stop_reason=stop_reason)
    store.append(Event(session_id=session.session_id, seq=0, type="session_end",
                       data={"stopped_by": stopped_by, "iterations": len(trace),
                             "answer": result.answer,
                             "stop_reason": stop_reason}))
    return result


async def _generate(
    provider: Any, messages: list[dict[str, Any]], definitions: list[dict[str, Any]],
    config: HarnessConfig, cache: Any | None, seed: int = 0,
) -> Any:
    if cache is None:
        return await provider.generate(messages, definitions, config)
    from ..providers.cache import cache_key

    key = cache_key(str(getattr(provider, "model", "fake")),
                    messages, definitions, config, seed)
    hit = cache.get(key)
    if hit is not None:
        from ..providers.base import ModelResponse

        return ModelResponse(**hit)
    resp = await provider.generate(messages, definitions, config)
    cache.put(key, resp.model_dump() if hasattr(resp, "model_dump") else dict(resp))
    return resp
