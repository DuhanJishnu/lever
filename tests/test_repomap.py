import sys

sys.path.insert(0, "src")

from lever.context.repomap import (
    build_graph,
    build_repomap,
    collect_files,
    pagerank,
    scan_file,
)


def _ws(tmp_path):
    (tmp_path / "a.py").write_text(
        "def helper(x):\n    return x * 2\n\n\ndef run(x):\n    return helper(x) + 1\n",
        encoding="utf-8",
    )
    (tmp_path / "b.py").write_text(
        "from a import helper\n\n\ndef run2(x):\n    return helper(x) - 1\n",
        encoding="utf-8",
    )
    return tmp_path


def test_scan_defs_refs_signatures(tmp_path):
    _ws(tmp_path)
    info = scan_file(tmp_path / "a.py")
    assert info["ok"] is True
    names = [(k, n) for k, n, _ln, _s in info["defs"]]
    assert ("def", "helper") in names and ("def", "run") in names
    assert "helper" in info["refs"]
    sigs = {n: s for _k, n, _ln, s in info["defs"]}
    assert sigs["helper"] == "(x)"


def test_graph_edges_follow_definitions(tmp_path):
    _ws(tmp_path)
    files = collect_files(tmp_path)
    assert len(files) == 2
    edges = build_graph(files, tmp_path)
    assert "a.py" in edges["b.py"]  # b uses helper defined in a
    assert "b.py" not in edges["a.py"]


def test_pagerank_personalization(tmp_path):
    _ws(tmp_path)
    files = collect_files(tmp_path)
    rels = ["a.py", "b.py"]
    edges = build_graph(files, tmp_path)
    plain = pagerank(rels, edges, {})
    biased = pagerank(rels, edges, {"b.py": 9.0, "a.py": 1.0})
    assert biased["b.py"] > plain["b.py"]


def test_repomap_budget_and_mention_boost(tmp_path):
    _ws(tmp_path)
    full = build_repomap(tmp_path, task="fix the helper in a")
    assert "a.py" in full and "def helper(x)" in full
    assert full.index("a.py") < full.index("b.py")  # mentioned file ranks first
    tiny = build_repomap(tmp_path, budget_tokens=10)
    assert "budget" in tiny
    assert len(tiny) <= 10 * 4 + 200


def test_repomap_empty_workspace(tmp_path):
    assert build_repomap(tmp_path) == "(empty workspace)"


def test_repomap_skips_caches(tmp_path):
    _ws(tmp_path)
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "junk.py").write_text("x = 1\n", encoding="utf-8")
    assert "junk.py" not in build_repomap(tmp_path)


def _history(n_tool: int) -> list[dict]:
    msgs: list[dict] = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "task"},
    ]
    for i in range(n_tool):
        msgs.append({"role": "assistant", "content": "",
                     "tool_calls": [{"name": "bash", "args": {}}]})
        msgs.append({"role": "tool", "name": "bash",
                     "content": f"output number {i}\nline2\nline3"})
    return msgs


def test_masking_keeps_last_k():
    from lever.context.masking import mask_observations

    masked, n = mask_observations(_history(10), keep_last=6)
    assert n == 4
    tools = [m for m in masked if m.get("role") == "tool"]
    assert len(tools) == 10
    assert all("elided" in t["content"] for t in tools[:4])
    assert all("output number" in t["content"] for t in tools[4:])
    ph = tools[0]["content"]
    assert "bash" in ph and "Re-run if needed" in ph


def test_masking_never_touches_reasoning():
    from lever.context.masking import mask_observations

    masked, n = mask_observations(_history(10), keep_last=2)
    assert n == 8
    assistants = [m for m in masked if m.get("role") == "assistant"]
    assert len(assistants) == 10
    assert all(m.get("tool_calls") for m in assistants)  # calls intact
    assert masked[0]["content"] == "sys" and masked[1]["content"] == "task"


def test_masking_short_history_untouched():
    from lever.context.masking import mask_observations

    msgs = _history(2)
    masked, n = mask_observations(msgs, keep_last=6)
    assert n == 0 and masked == msgs
    # input never mutated
    assert "elided" not in msgs[3]["content"]
