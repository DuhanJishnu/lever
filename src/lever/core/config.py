"""HarnessConfig — every harness feature is a toggle (ablation ladder B0..B8)."""

from __future__ import annotations

from pydantic import BaseModel


class HarnessConfig(BaseModel):
    model: str = "gemini-2.5-flash"
    temperature: float = 0.2
    thinking_budget: int | None = None  # keep IDENTICAL across ablations
    max_steps: int = 40
    context_budget_tokens: int = 60_000

    # ---- feature toggles (each is one ablation step) ----
    tolerant_edit: bool = False      # B1
    repo_map: bool = False           # B3 (B2 has no config flag: truncation is B0 default)
    output_truncation: bool = False  # B2 (ranged reads + head/tail truncation)
    observation_masking: bool = False  # B4
    compaction: bool = False         # B5
    verify_loop: bool = False        # B6
    planner_prompt: bool = False     # B7
    loop_guard: bool = False         # B8
    best_of_n: int = 1
    prompt_version: str = "v1"

    @classmethod
    def b0(cls, **overrides: object) -> HarnessConfig:
        """Bare baseline: all toggles off."""
        base = cls(
            tolerant_edit=False,
            repo_map=False,
            output_truncation=False,
            observation_masking=False,
            compaction=False,
            verify_loop=False,
            planner_prompt=False,
            loop_guard=False,
            best_of_n=1,
            prompt_version="v1",
        )
        if overrides:
            return base.model_copy(update=overrides)  # type: ignore[arg-type]
        return base
