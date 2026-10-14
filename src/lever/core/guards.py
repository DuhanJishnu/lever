"""Composable guardrail functions + repetition tracker (B8).

Two layers:
1. HARD guards — pure functions `guard(state) -> continue | stop(reason)`,
   evaluated BEFORE every model call; first `stop` wins. Structural, the model
   cannot bypass them.
2. SOFT repetition handling — `RepeatTracker` (stateful, owned by the loop).
   Repeated calls first earn a nudge message, then a forced re-plan prompt,
   then a stop. The loop delivers nudges as harness user messages AND
   `harness_nudge` events so the log stays honest.

All thresholds are module constants (documented below), identical across
ablation configs — the ladder varies FEATURES, never trip points.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

# ---- trip points (constant across configs) ----
MAX_CONTEXT_MESSAGES = 300   # hard stop: history longer than this is rot
TIME_LIMIT_S = 600.0         # hard stop: 10 min wall per run
REPEAT_WINDOW = 5            # look back this many turns for repeats
REPEAT_COUNT = 3             # same call this often in-window -> trigger
MAX_NUDGES = 2               # nudge, nudge, then re-plan, then stop
REPLAN_TRIGGER = MAX_NUDGES + 1

# Tool-result prefixes/markers that count as FAILURE for streak detection.
# Conservative: only unambiguous failure signals, never "No matches" (grep can
# legitimately find nothing) or empty outputs.
FAILURE_MARKERS = (
    "Error in ",
    "Unknown tool",
    "REVERTED",
    "not found",
    "matches ",
    "timed out",
    "empty range",
    "no such file",
    "no such path",
)


@dataclass(frozen=True)
class GuardResult:
    verdict: Literal["continue", "stop"]
    reason: str = ""

    @staticmethod
    def go() -> GuardResult:
        return GuardResult("continue")

    @staticmethod
    def stop_with(reason: str) -> GuardResult:
        return GuardResult("stop", reason)


@dataclass
class LoopState:
    iterations: int
    max_steps: int
    context_messages: int = 0
    est_tokens: int = 0
    elapsed_s: float = 0.0
    history: tuple[str, ...] = ()  # call keys, oldest-first


Guard = Callable[[LoopState], GuardResult]


def compose_guards(*guards: Guard) -> Guard:
    def _composed(state: LoopState) -> GuardResult:
        for g in guards:
            r = g(state)
            if r.verdict == "stop":
                return r
        return GuardResult.go()

    return _composed


def max_steps_guard(state: LoopState) -> GuardResult:
    if state.iterations >= state.max_steps:
        return GuardResult.stop_with(f"max_steps reached ({state.max_steps})")
    return GuardResult.go()


def max_context_messages(n: int = MAX_CONTEXT_MESSAGES) -> Guard:
    def _guard(state: LoopState) -> GuardResult:
        if state.context_messages >= n:
            return GuardResult.stop_with(
                f"context messages {state.context_messages} >= {n}")
        return GuardResult.go()

    return _guard


def max_tokens_guard(budget: int) -> Guard:
    def _guard(state: LoopState) -> GuardResult:
        if state.est_tokens >= budget:
            return GuardResult.stop_with(
                f"estimated tokens {state.est_tokens} >= budget {budget}")
        return GuardResult.go()

    return _guard


def time_limit_guard(seconds: float = TIME_LIMIT_S) -> Guard:
    def _guard(state: LoopState) -> GuardResult:
        if state.elapsed_s >= seconds:
            return GuardResult.stop_with(
                f"elapsed {state.elapsed_s:.0f}s >= limit {seconds:.0f}s")
        return GuardResult.go()

    return _guard


def call_key(tool: str, args: Any) -> str:
    """Stable identity for (tool, args): normalized JSON, str fallback."""
    try:
        return tool + ":" + json.dumps(args or {}, sort_keys=True, default=str)
    except (TypeError, ValueError):
        return tool + ":" + repr(args)


def is_failure(result: str) -> bool:
    """Heuristic: unambiguous failure signals anywhere in the result text."""
    return any(m in result for m in FAILURE_MARKERS)


ActionKind = Literal["none", "nudge", "replan", "stop"]


@dataclass
class RepeatTracker:
    """Counts repeated calls over a sliding window; escalates nudge->replan->stop.

    A trigger fires when the latest turn's call set already appeared
    REPEAT_COUNT times within REPEAT_WINDOW turns (same multiset of keys), or
    when every call in the latest turn failed and that also happened on the
    previous turn (failure pairs — weak models often alternate two doomed calls,
    which consecutive-identical detection misses).
    """

    window: int = REPEAT_WINDOW
    count: int = REPEAT_COUNT
    max_nudges: int = MAX_NUDGES
    turns: list[tuple[tuple[str, ...], bool]] = field(default_factory=list)
    triggers: int = 0

    def update(self, keys: list[str], all_failed: bool) -> tuple[ActionKind, str]:
        self.turns.append((tuple(sorted(keys)), all_failed))
        self.turns = self.turns[-self.window:]
        if not self._triggered():
            return ("none", "")
        self.triggers += 1
        if self.triggers <= self.max_nudges:
            return ("nudge", self._nudge_text())
        if self.triggers == REPLAN_TRIGGER:
            return ("replan", self._replan_text())
        return ("stop", self._stop_text())

    def _triggered(self) -> bool:
        if len(self.turns) < 2:
            return False
        latest, latest_failed = self.turns[-1]
        if not latest:
            return False
        same = sum(1 for keys, _ in self.turns if keys == latest)
        if same >= self.count:
            return True
        # failure pairs: this turn and last turn both fully failed
        return bool(latest_failed and len(self.turns) >= 2 and self.turns[-2][1])

    def _describe(self) -> str:
        latest = self.turns[-1][0] if self.turns else ()
        shown = ", ".join(latest[:2])
        more = f" (+{len(latest) - 2} more)" if len(latest) > 2 else ""
        return shown + more

    def _nudge_text(self) -> str:
        return (
            f"[harness] You already ran {self._describe()} several times and "
            f"the situation is not changing. Stop repeating it: re-read the "
            f"relevant file or error output and try a DIFFERENT approach."
        )

    def _replan_text(self) -> str:
        return (
            "[harness] Reminders haven't helped. Before your next tool call, "
            "write a 3-line re-plan: (1) what you have tried, (2) why it "
            "failed, (3) the one different thing you will try next. Then do "
            "ONLY that next step."
        )

    def _stop_text(self) -> str:
        return (
            f"repetition without progress after {self.triggers} interventions "
            f"(last: {self._describe()})"
        )
