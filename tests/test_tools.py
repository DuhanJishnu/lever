import sys
from types import SimpleNamespace

sys.path.insert(0, "src")

import pytest

from lever.tools.registry import create_tools


def _tolerant(tmp_path):
    return create_tools(tmp_path, SimpleNamespace(tolerant_edit=True))


def _trunc(tmp_path):
    return create_tools(tmp_path, SimpleNamespace(output_truncation=True))


def test_path_escape_rejected(tmp_path):
    reg = create_tools(tmp_path)
    (tmp_path / "ok.txt").write_text("hello", encoding="utf-8")
    assert "hello" in __import__("asyncio").run(
        reg.run("read_file", {"path": "ok.txt"})
    )
    out = __import__("asyncio").run(reg.run("read_file", {"path": "../evil.txt"}))
    assert "escapes workspace" in out


def test_write_read_edit_exact(tmp_path):
    import asyncio

    reg = create_tools(tmp_path)
    assert "Wrote" in asyncio.run(
        reg.run("write_file", {"path": "a/b.txt", "content": "line1\nline2\n"})
    )
    assert "line1" in asyncio.run(reg.run("read_file", {"path": "a/b.txt"}))
    out = asyncio.run(
        reg.run("edit_file", {"path": "a/b.txt", "old_str": "line1", "new_str": "LINE1"})
    )
    assert "Edit applied" in out
    assert "LINE1" in (tmp_path / "a" / "b.txt").read_text(encoding="utf-8")
    # Miss + ambiguous errors are model-friendly, not exceptions
    assert "not found" in asyncio.run(
        reg.run("edit_file", {"path": "a/b.txt", "old_str": "zzz", "new_str": "q"})
    )
    asyncio.run(reg.run("write_file", {"path": "c.txt", "content": "x\nx\n"}))
    assert "2 locations" in asyncio.run(
        reg.run("edit_file", {"path": "c.txt", "old_str": "x", "new_str": "y"})
    )


def test_grep_and_bash(tmp_path):
    import asyncio

    reg = create_tools(tmp_path)
    (tmp_path / "m.py").write_text("def foo():\n    pass\n", encoding="utf-8")
    out = asyncio.run(reg.run("grep", {"pattern": "def foo"}))
    assert "m.py:1" in out
    assert "No matches" in asyncio.run(reg.run("grep", {"pattern": "zzz_nope"}))
    assert "invalid regex" in asyncio.run(reg.run("grep", {"pattern": "(["}))
    bash = asyncio.run(reg.run("bash", {"cmd": "echo hi"}))
    assert "exit=0" in bash and "hi" in bash
    assert "timed out" in asyncio.run(
        reg.run("bash", {"cmd": "python -c \"import time; time.sleep(5)\"", "timeout": 1})
    )


def test_unknown_tool(tmp_path):
    import asyncio

    reg = create_tools(tmp_path)
    out = asyncio.run(reg.run("nope", {}))
    assert "Unknown tool" in out and "read_file" in out


@pytest.mark.asyncio
async def test_output_cap(tmp_path, monkeypatch):
    from lever.tools import base

    monkeypatch.setattr(base, "MAX_OUTPUT_CHARS", 20)
    reg = create_tools(tmp_path)
    (tmp_path / "big.txt").write_text("z" * 100, encoding="utf-8")
    out = await reg.run("read_file", {"path": "big.txt"})
    assert "truncated" in out


@pytest.mark.asyncio
async def test_b1_whitespace_insensitive_match(tmp_path):
    reg = _tolerant(tmp_path)
    (tmp_path / "f.py").write_text("def f():\n    return 1   \n", encoding="utf-8")
    out = await reg.run("edit_file", {
        "path": "f.py", "old_str": "def f():\n  return 1", "new_str": "def f():\n  return 2",
    })
    assert "Edit applied" in out and "whitespace" in out
    assert (tmp_path / "f.py").read_text(encoding="utf-8") == "def f():\n  return 2"


@pytest.mark.asyncio
async def test_b1_fuzzy_match_small_typo(tmp_path):
    reg = _tolerant(tmp_path)
    (tmp_path / "g.py").write_text(
        "def total(n):\n    return sum(range(n + 1))\n", encoding="utf-8")
    await reg.run("edit_file", {
        "path": "g.py",
        "old_str": "def total(n):\n    return sum(range(n + 1))",
        "new_str": "def total(n):\n    return sum(range(n + 2))",
    })
    # exact hit here; now a real typo that still clears 0.9
    (tmp_path / "h.py").write_text("result = compute_total(items)\n", encoding="utf-8")
    out2 = await reg.run("edit_file", {
        "path": "h.py",
        "old_str": "result = compute_totals(items)\n",
        "new_str": "result = compute_total(items, fast=True)\n",
    })
    assert "Edit applied" in out2 and "fuzzy" in out2


@pytest.mark.asyncio
async def test_b1_ambiguous_reports_lines(tmp_path):
    reg = _tolerant(tmp_path)
    (tmp_path / "d.py").write_text("x = 1\ny = 2\nx = 1\n", encoding="utf-8")
    out = await reg.run("edit_file", {"path": "d.py", "old_str": "x = 1",
                                      "new_str": "x = 9"})
    assert "2 locations" in out and "replace_all" in out
    assert (tmp_path / "d.py").read_text(encoding="utf-8") == "x = 1\ny = 2\nx = 1\n"


@pytest.mark.asyncio
async def test_b1_replace_all(tmp_path):
    reg = _tolerant(tmp_path)
    (tmp_path / "d.py").write_text("x = 1\ny = 2\nx = 1\n", encoding="utf-8")
    out = await reg.run("edit_file", {"path": "d.py", "old_str": "x = 1",
                                      "new_str": "x = 9", "replace_all": True})
    assert "Edit applied" in out
    assert (tmp_path / "d.py").read_text(encoding="utf-8") == "x = 9\ny = 2\nx = 9\n"


@pytest.mark.asyncio
async def test_b1_syntax_revert(tmp_path):
    reg = _tolerant(tmp_path)
    before = "x = 1\nprint(x)\n"
    (tmp_path / "s.py").write_text(before, encoding="utf-8")
    out = await reg.run("edit_file", {"path": "s.py", "old_str": "x = 1",
                                      "new_str": "x = "})
    assert "REVERTED" in out and "line 1" in out
    assert (tmp_path / "s.py").read_text(encoding="utf-8") == before


@pytest.mark.asyncio
async def test_b1_miss_reports_closest(tmp_path):
    reg = _tolerant(tmp_path)
    (tmp_path / "m.py").write_text(
        "def alpha():\n    return 1\n\n\ndef beta():\n    return 2\n",
        encoding="utf-8")
    out = await reg.run("edit_file", {
        "path": "m.py",
        "old_str": "def gamma():\n    return 3\n    extra_line_here = True\n",
        "new_str": "x",
    })
    assert "Closest match at lines" in out and "similarity" in out


@pytest.mark.asyncio
async def test_b0_stays_exact(tmp_path):
    reg = create_tools(tmp_path)  # tolerant off by default
    (tmp_path / "f.py").write_text("a = 1\n", encoding="utf-8")
    out = await reg.run("edit_file", {"path": "f.py", "old_str": "a  =  1",
                                      "new_str": "a = 2"})
    assert "exact match required" in out
    assert (tmp_path / "f.py").read_text(encoding="utf-8") == "a = 1\n"


@pytest.mark.asyncio
async def test_grep_relative_workspace_root(tmp_path, monkeypatch):
    """Regression: grep crashed with relative roots (rglob absolute vs
    relative_to relative) — the exact shape the eval runner uses."""
    from pathlib import Path

    monkeypatch.chdir(tmp_path)
    (tmp_path / "ws").mkdir()
    (tmp_path / "ws" / "m.py").write_text("def foo():\n    pass\n", encoding="utf-8")
    reg = create_tools(Path("ws"))
    out = await reg.run("grep", {"pattern": "def foo"})
    assert "m.py:1" in out
    assert "not in the subpath" not in out


@pytest.mark.asyncio
async def test_b2_ranged_read(tmp_path):
    reg = _trunc(tmp_path)
    (tmp_path / "big.py").write_text(
        "\n".join(f"line {i}" for i in range(1, 251)) + "\n", encoding="utf-8")
    # default: first 100 + pointer
    out = await reg.run("read_file", {"path": "big.py"})
    assert "lines 1-100 of 250" in out and "start_line=101" in out
    assert "line 100\n" in out and "line 101\n" not in out
    # explicit range
    out2 = await reg.run("read_file", {"path": "big.py",
                                       "start_line": 200, "end_line": 250})
    assert "lines 200-250 of 250" in out2 and "line 200" in out2
    # small file: whole content, no wrapper
    (tmp_path / "small.py").write_text("a = 1\n", encoding="utf-8")
    assert await reg.run("read_file", {"path": "small.py"}) == "a = 1\n"
    # inverted range
    out3 = await reg.run("read_file", {"path": "big.py",
                                       "start_line": 50, "end_line": 10})
    assert "empty range" in out3


@pytest.mark.asyncio
async def test_b2_head_tail_truncation(tmp_path, monkeypatch):
    from lever.tools import base

    monkeypatch.setattr(base, "HEAD_LINES", 10)
    monkeypatch.setattr(base, "TAIL_LINES", 5)
    reg = _trunc(tmp_path)
    (tmp_path / "out.txt").write_text(
        "\n".join(f"L{i}" for i in range(50)) + "\n", encoding="utf-8")
    out = await reg.run("read_file", {"path": "out.txt",
                                      "start_line": 1, "end_line": 50})
    assert "lines omitted" in out
    assert "L0" in out and "L49" in out and "L25" not in out


@pytest.mark.asyncio
async def test_b0_read_unchanged(tmp_path):
    reg = create_tools(tmp_path)
    (tmp_path / "f.py").write_text("a = 1\nb = 2\n", encoding="utf-8")
    assert await reg.run("read_file", {"path": "f.py"}) == "a = 1\nb = 2\n"
