"""B4 observation masking: bound history growth from tool outputs.

Policy: keep the last K tool results in full; replace older ones with a
one-line placeholder. Assistant reasoning and tool CALLS are never masked
(cheap and load-bearing for coherence). Masking applies ONLY to the
provider-bound copy — events always keep the full text (replay fidelity).

API-safety: masked messages keep their position and role, so call/response
pairing stays valid on every provider (Gemini requires each FunctionResponse
to follow its FunctionCall; OpenAI needs tool_call_id linkage).
"""

from __future__ import annotations

from typing import Any

# Last N tool results survive in full. 6 covers ~2 recent turns of typical
# 2-3 calls/turn while bounding growth on 40-step thrash runs.
MASK_KEEP_LAST = 6


def mask_observations(
    messages: list[dict[str, Any]], keep_last: int = MASK_KEEP_LAST
) -> tuple[list[dict[str, Any]], int]:
    """Return (masked_copy, n_masked). Input never mutated."""
    tool_idx = [i for i, m in enumerate(messages) if m.get("role") == "tool"]
    mask_these = set(tool_idx[:-keep_last] if keep_last >= 0 else tool_idx)
    if not mask_these:
        return messages, 0
    out: list[dict[str, Any]] = []
    masked = 0
    for i, m in enumerate(messages):
        if i in mask_these:
            content = str(m.get("content", ""))
            lines = content.count("\n") + (1 if content else 0)
            out.append({
                "role": "tool",
                "name": m.get("name", ""),
                "content": (
                    f"[output of {m.get('name', 'tool')} elided "
                    f"({lines} lines, {len(content)} chars). "
                    f"Re-run if needed.]"
                ),
            })
            masked += 1
        else:
            out.append(dict(m))
    return out, masked
