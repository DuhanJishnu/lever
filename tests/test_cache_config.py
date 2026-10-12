import sys

sys.path.insert(0, "src")

from lever.core.config import HarnessConfig
from lever.providers.cache import ResponseCache, cache_key


def test_cache_hit_and_persistence(tmp_path):
    p = tmp_path / "c.jsonl"
    c1 = ResponseCache(p)
    cfg = HarnessConfig()
    msgs = [{"role": "user", "content": "say hi"}]
    key = cache_key("test-model", msgs, [], cfg)
    assert c1.get(key) is None
    c1.put(key, {"text": "hi", "tool_calls": []})
    assert c1.get(key) == {"text": "hi", "tool_calls": []}
    # Persisted across instances
    c2 = ResponseCache(p)
    assert c2.get(key) == {"text": "hi", "tool_calls": []}


def test_b0_all_toggles_off():
    cfg = HarnessConfig.b0()
    assert not any(
        [
            cfg.tolerant_edit,
            cfg.repo_map,
            cfg.output_truncation,
            cfg.observation_masking,
            cfg.compaction,
            cfg.verify_loop,
            cfg.planner_prompt,
            cfg.loop_guard,
        ]
    )
    assert cfg.best_of_n == 1
