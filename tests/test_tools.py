import sys

sys.path.insert(0, "src")

import pytest

from lever.tools.registry import create_tools


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
