"""B5 compaction with pinned memory: survive long histories.

Tier model (v1, explicit):
- PINNED (never compacted): messages[0] (system: prompt + repo map) and
  messages[1] (the task statement). Constraints/plan live here too.
- TAIL (kept verbatim): last TAIL_KEEP messages (~2 recent turns).
- MIDDLE (compactable): everything between, replaced by one LLM-written
  state note when the 70%-of-budget tripwire fires.

Compaction ladder per firing: summarize middle (fixed schema) -> if still
over budget, head/tail-truncate kept tool outputs (B2 primitive reused).
The loop emits `context_compacted` {before, after} so the UI meter and evals
can track it. Pure function + one provider call; loop owns events.

Token accounting uses the cheap local estimate (chars//4), NOT a metered
count_tokens call per turn — exactness is unnecessary for a 70% tripwire and
an extra API call per turn would double eval spend. Documented deviation.
"""

from __future__ import annotations

from typing import Any

# Trip at 70% of budget; keep ~2 turns verbatim after each compaction.
COMPACTION_THRESHOLD = 0.7
TAIL_KEEP_MESSAGES = 4

SUMMARY_PROMPT = """Summarize this coding-agent run so far into a state note. \
Be terse and factual; keep file paths and test outcomes exact. \
Use EXACTLY this format:

GOAL: ...
DECISIONS MADE: ...
FILES MODIFIED (with 1-line why): ...
TEST STATUS: ...
OPEN ISSUES: ...
NEXT STEPS: ..."""


def needs_compaction(est_tokens: int, budget_tokens: int) -> bool:
    return budget_tokens > 0 and est_tokens >= budget_tokens * COMPACTION_THRESHOLD


def split_tiers(messages: list[dict[str, Any]]) -> tuple[
        list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """(pinned, middle, tail). Pinned = first 2; tail = last TAIL_KEEP."""
    if len(messages) <= 2:
        return (list(messages), [], [])
    pinned, rest = messages[:2], messages[2:]
    if len(rest) <= TAIL_KEEP_MESSAGES:
        return (pinned, [], rest)
    return (pinned, rest[:-TAIL_KEEP_MESSAGES], rest[-TAIL_KEEP_MESSAGES:])


def render_turn(m: dict[str, Any]) -> str:
    role = m.get("role", "?")
    text = str(m.get("content", ""))
    calls = m.get("tool_calls") or []
    if calls:
        names = ", ".join(
            c.get("name", "?") if isinstance(c, dict) else str(c) for c in calls)
        text = (text + f" [calls: {names}]") if text else f"[calls: {names}]"
    return f"{role}: {text[:2000]}"


async def compact_history(
    messages: list[dict[str, Any]],
    provider: Any,
    config: Any = None,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Shrink history past the tripwire. Returns (new_messages, info|None).
    info carries before/after estimates for the `context_compacted` event.
    """

    def est(msgs: list[dict[str, Any]]) -> int:
        return max(1, sum(len(str(m.get("content", ""))) for m in msgs) // 4)

    pinned, middle, tail = split_tiers(messages)
    if not middle:
        return messages, None
    from ..tools.base import truncate_lines  # local import: one-way dep only

    before = est(messages)
    transcript = "\n".join(render_turn(m) for m in middle)
    summary_messages = [
        {"role": "system", "content": SUMMARY_PROMPT},
        {"role": "user", "content": transcript},
    ]
    resp = await provider.generate(summary_messages, [], config)
    note = str(getattr(resp, "text", "") or "").strip() or "(empty summary)"
    note_msg = {"role": "user",
                "content": "[harness: context compacted — state note]\n" + note}
    shrunk = pinned + [note_msg] + tail
    budget = int(getattr(config, "context_budget_tokens", 0) or 0)
    if budget > 0 and est(shrunk) >= budget * COMPACTION_THRESHOLD:
        # Ladder rung 2: permanently truncate the biggest kept outputs.
        shrunk = pinned + [note_msg] + [
            {**m, "content": truncate_lines(str(m.get("content", "")))}
            if m.get("role") == "tool" else m for m in tail
        ]
    after = est(shrunk)
    return shrunk, {"before": before, "after": after,
                    "dropped": len(middle), "note_chars": len(note)}
