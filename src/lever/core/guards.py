"""Composable guardrail functions (skeletal in B0, full ladder in B8).

Each guard inspects loop state and returns continue | stop(reason). Guards run
BEFORE every model call; the first `stop` wins and is recorded as `stopped_by`.
B0 ships only max_steps (part of the baseline); B8 adds repetition, context,
budget, and time guards on this exact interface.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal


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


Guard = Callable[[LoopState], GuardResult]


def max_steps_guard(state: LoopState) -> GuardResult:
    if state.iterations >= state.max_steps:
        return GuardResult.stop_with(f"max_steps reached ({state.max_steps})")
    return GuardResult.go()


def compose_guards(*guards: Guard) -> Guard:
    def _composed(state: LoopState) -> GuardResult:
        for g in guards:
            r = g(state)
            if r.verdict == "stop":
                return r
        return GuardResult.go()

    return _composed
