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
