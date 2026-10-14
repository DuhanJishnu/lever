"""Policy engine: code-level guardrails (policies live in code, not prompts).

Interface: Rule.evaluate(history, call) -> allow | deny(reason) | ask(reason).
The engine returns the FIRST non-allow verdict (order rules deny-first).
History is the session's event log itself — stateful rules (budgets,
install-then-push) derive state by scanning events, so no side store exists
to drift out of sync. Every decision surfaces as an event downstream.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol


@dataclass(frozen=True)
class ProposedCall:
    tool: str
    args: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Decision:
    verdict: Literal["allow", "deny", "ask"]
    reason: str = ""

    @staticmethod
    def allow() -> Decision:
        return Decision("allow")

    @staticmethod
    def deny(reason: str) -> Decision:
        return Decision("deny", reason)

    @staticmethod
    def ask(reason: str) -> Decision:
        return Decision("ask", reason)


class Rule(Protocol):
    def evaluate(self, history: list[Any], call: ProposedCall) -> Decision: ...


class PolicyEngine:
    def __init__(self, rules: list[Rule] | None = None) -> None:
        self.rules = list(rules or [])

    def evaluate(self, history: list[Any], call: ProposedCall) -> Decision:
        for rule in self.rules:
            decision = rule.evaluate(history, call)
            if decision.verdict != "allow":
                return decision
        return Decision.allow()
