"""Phase 0 acceptance: 'say hi' through provider -> events in SQLite; 2nd run hits cache.

Usage:
    uv run python scripts/say_hi.py --prompt "say hi" --db .lever_events.db
    Set GEMINI_API_KEY in .env for real calls; otherwise --fake uses FakeProvider.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

sys.path.insert(0, "src")
from dotenv import load_dotenv  # type: ignore[import-not-found]

from lever.core.config import HarnessConfig
from lever.core.events import Event, new_session_id
from lever.providers.base import ModelResponse
from lever.providers.cache import ResponseCache, cache_key
from lever.store.sqlite import EventStore


async def main() -> None:
    load_dotenv()
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt", default="say hi")
    ap.add_argument("--db", default=".lever_events.db")
    ap.add_argument("--cache", default=".lever_cache.jsonl")
    ap.add_argument("--fake", action="store_true")
    ap.add_argument("--session", default=None)
    args = ap.parse_args()

    use_fake = args.fake or not os.getenv("GEMINI_API_KEY")
    config = HarnessConfig()
    messages = [{"role": "user", "content": args.prompt}]
    tools: list[dict] = []
    model_name = "fake" if use_fake else os.getenv("LEVER_MODEL", "")
    if not model_name:
        raise ValueError("LEVER_MODEL is not set (see .env.example)")
    key = cache_key(model_name, messages, tools, config)
    cache = ResponseCache(args.cache)

    session_id = args.session or new_session_id()
    store = EventStore(args.db)
    store.append(
        Event(session_id=session_id, seq=0, type="user_message",
              data={"content": args.prompt})
    )

    cached = cache.get(key)
    if cached is not None:
        resp = ModelResponse(**cached)
        print(f"CACHE HIT key={key[:12]} session={session_id}")
    else:
        store.append(
            Event(session_id=session_id, seq=0, type="model_request",
                  data={"messages": messages, "model": model_name})
        )
        if use_fake:
            from lever.providers.fake import FakeProvider

            provider = FakeProvider.say_hi()
            print("USING FakeProvider (no GEMINI_API_KEY or --fake)")
        else:
            from lever.providers.gemini import GeminiProvider

            provider = GeminiProvider()  # type: ignore[assignment]
        resp = await provider.generate(messages, tools, config)  # type: ignore[union-attr]
        cache.put(key, resp.model_dump())
        print(f"CACHE MISS key={key[:12]} session={session_id}")

    store.append(
        Event(session_id=session_id, seq=0, type="model_response",
              data=resp.model_dump())
    )
    print(f"MODEL: {resp.text}")
    print(f"EVENTS in {args.db} for session {session_id}: {len(store.read(session_id))}")
    print(f"cache hits={cache.hits} misses={cache.misses}")
    store.close()


if __name__ == "__main__":
    asyncio.run(main())
