"""On-disk LLM response cache: hash(model, messages, tools, config) -> response.

Saves money for the whole project. Cache hits skip the API call.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def cache_key(
    model: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]],
    config: Any, seed: int = 0,
) -> str:
    cfg: dict[str, Any] = {}
    if config is not None:
        try:
            cfg = config.model_dump()  # pydantic
        except Exception:
            cfg = {"repr": repr(config)}
    payload = json.dumps(
        {"model": model, "messages": messages, "tools": tools,
         "config": cfg, "seed": seed},
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


class ResponseCache:
    def __init__(self, path: str | Path = ".lever_cache.jsonl") -> None:
        self.path = Path(path)
        self._mem: dict[str, dict[str, Any]] = {}
        self.hits = 0
        self.misses = 0
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                try:
                    row = json.loads(line)
                    self._mem[row["key"]] = row["response"]
                except Exception:
                    continue

    def get(self, key: str) -> dict[str, Any] | None:
        hit = self._mem.get(key)
        if hit is not None:
            self.hits += 1
        else:
            self.misses += 1
        return hit

    def put(self, key: str, response: dict[str, Any]) -> None:
        self._mem[key] = response
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"key": key, "response": response}, default=str) + "\n")
