"""edit_file tool — exact match in B0; tolerant cascade behind `tolerant_edit` (B1).

Cascade (stops at first success):
  1. Exact match of `old_str` (unique, or all with `replace_all`).
  2. Whitespace-insensitive match (trailing whitespace + indentation
     normalized), applied only if exactly one candidate window.
  3. Fuzzy line-window match (`difflib.SequenceMatcher` ratio >= 0.9),
     applied only if exactly one candidate window.
  4. Structured failure: closest window + lines + similarity + snippet.

After any successful edit of a `.py` file, the result is syntax-checked
(`compile()` — never executed). A breaking edit is reverted and reported
with the exact line, so the model can retry rather than debug fallout.
"""

from __future__ import annotations

import difflib
from pathlib import Path
from typing import Any

from .base import Tool, resolve_safe

FUZZY_THRESHOLD = 0.9
MAX_LOCATIONS_SHOWN = 5


def make_edit_tool(root: Path, tolerant: bool = False) -> Tool:
    async def _run(args: dict[str, Any]) -> str:
        path = resolve_safe(root, str(args.get("path", "")))
        old = str(args.get("old_str", ""))
        new = str(args.get("new_str", ""))
        replace_all = bool(args.get("replace_all", False))
        if not path.is_file():
            return f"edit_file: no such file: {args.get('path')!r}."
        if not old:
            return "edit_file: old_str is empty. Provide the exact block to replace."
        content = path.read_text(encoding="utf-8", errors="replace")

        # ---- stage 1: exact ----
        hits = content.count(old)
        if hits == 1 and not replace_all:
            return _apply(path, args.get("path"), content,
                          content.replace(old, new, 1),
                          old_block=old, new_block=new)
        if hits > 1:
            if replace_all:
                return _apply(path, args.get("path"), content,
                              content.replace(old, new),
                              old_block=old, new_block=new)
            locs = _locations(content, old)
            shown = ", ".join(f"line {n}" for n in locs[:MAX_LOCATIONS_SHOWN])
            extra = (f" (+{len(locs) - MAX_LOCATIONS_SHOWN} more)"
                     if len(locs) > MAX_LOCATIONS_SHOWN else "")
            return (
                f"edit_file: old_str matches {hits} locations ({shown}{extra}). "
                "Add more surrounding context to make it unique, "
                "or set replace_all=true to replace every occurrence."
            )
        # hits == 0 from here on
        if not tolerant:
            hint = ""
            try:
                best = _fuzzy_candidates(content, old)
                if best:
                    (s, e, score) = best[0]
                    snippet = content[s:e].strip().splitlines()
                    preview = "\n".join(snippet[:6])
                    ls, le = _line_range(content, s, e)
                    hint = (f" Closest match at lines {ls}-{le} "
                            f"(similarity {score:.2f}):\n{preview}")
            except (ValueError, IndexError):
                hint = ""
            return (
                "edit_file: old_str not found (exact match required in B0). "
                "Re-read the file and copy the block exactly, including whitespace."
                + hint
            )

        # ---- stage 2: whitespace-insensitive (unique candidate only) ----
        stage2 = _ws_candidates(content, old)
        if len(stage2) == 1:
            start, end = stage2[0]
            updated = content[:start] + new + content[end:]
            return _apply(path, args.get("path"), content, updated,
                          note="matched ignoring whitespace/indentation",
                          old_block=old, new_block=new)
        if len(stage2) > 1:
            shown = ", ".join(f"lines {a}-{b}" for a, b in stage2[:3])
            return (
                f"edit_file: old_str not found exactly; whitespace-insensitive "
                f"match is ambiguous ({shown}, ...). Add more context lines to "
                f"make it unique."
            )

        # ---- stage 3: fuzzy window (unique candidate above threshold only) ----
        best = _fuzzy_candidates(content, old)
        above = [t for t in best if t[2] >= FUZZY_THRESHOLD]
        if len(above) == 1:
            (start, end, score) = above[0]
            updated = content[:start] + new + content[end:]
            return _apply(path, args.get("path"), content, updated,
                          note=f"fuzzy match (similarity {score:.2f})",
                          old_block=old, new_block=new)
        if len(above) > 1:
            shown = ", ".join(
                f"lines {a}-{b}" for a, b in
                (_line_range(content, s, e) for s, e, _ in above[:3]))
            return (
                f"edit_file: old_str not found; fuzzy match is ambiguous "
                f"({shown}, ...). Add more context lines to make it unique."
            )
        if best:
            (start, end, score) = best[0]
            snippet = content[start:end].strip().splitlines()
            preview = "\n".join(snippet[:6])
            s, e = _line_range(content, start, end)
            return (
                f"edit_file: old_str not found. Closest match at lines {s}-{e} "
                f"(similarity {score:.2f}):\n{preview}\n"
                f"Re-read the file and retry with the exact block."
            )
        return (
            "edit_file: old_str not found, and no similar block exists. "
            "Re-read the file (paths may be wrong) and retry."
        )

    return Tool(
        name="edit_file",
        description=(
            "Replace a block of text in a file (old_str must match exactly once; "
            "set replace_all=true to replace every occurrence). "
            + (
                "Whitespace/indentation differences and small typos are tolerated "
                "(unique match required). "
                if tolerant else ""
            )
            + "Returns a unified diff. Python edits are syntax-checked."
        ),
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "old_str": {"type": "string"},
                "new_str": {"type": "string"},
                "replace_all": {"type": "boolean"},
            },
            "required": ["path", "old_str", "new_str"],
        },
        execute=_run,
    )


def _apply(path: Path, shown: Any, before: str, after: str, note: str = "",
             old_block: str = "", new_block: str = "") -> str:
    if after == before:
        return "Edit applied (no visible change)."
    if path.suffix == ".py":
        try:
            compile(after, str(path), "exec")
        except SyntaxError as e:
            return (
                f"edit_file: edit REVERTED — it would break Python syntax at "
                f"line {e.lineno}: {e.msg}. File unchanged; retry with a "
                f"syntactically valid replacement."
            )
    path.write_text(after, encoding="utf-8")
    diff = "".join(
        difflib.unified_diff(
            before.splitlines(True),
            after.splitlines(True),
            fromfile=f"a/{shown}",
            tofile=f"b/{shown}",
        )
    )
    prefix = f"Edit applied ({note}).\n" if note else "Edit applied.\n"
    out = prefix + diff if diff else prefix + "(no visible change)"
    warn = _rename_warning(after, old_block, new_block)
    return out + warn


def _rename_warning(after: str, old_block: str, new_block: str) -> str:
    """Warn when a `def` rename leaves stale call sites in the same file.

    compile() passes on dangling names (NameError is runtime), so without
    this the agent in your screenshot stops after renaming
    add_numbers -> sub_numbers while line 9 still calls add_numbers.
    """
    import re

    if not old_block or not new_block:
        return ""
    old_defs = re.findall(r"^\s*def\s+(\w+)\s*\(", old_block, re.MULTILINE)
    new_defs = re.findall(r"^\s*def\s+(\w+)\s*\(", new_block, re.MULTILINE)
    if len(old_defs) != 1 or len(new_defs) != 1:
        return ""
    old_name, new_name = old_defs[0], new_defs[0]
    if old_name == new_name:
        return ""
    if not re.search(rf"^\s*def\s+{re.escape(new_name)}\s*\(", after, re.MULTILINE):
        return ""
    lines = []
    for i, ln in enumerate(after.splitlines(), start=1):
        if re.search(rf"\b{re.escape(old_name)}\s*\(", ln) and \
                not re.search(rf"^\s*def\s+{re.escape(old_name)}\s*\(", ln):
            lines.append(str(i))
    if not lines:
        return ""
    return (
        f"\nWarning: `{old_name}` renamed to `{new_name}` but `{old_name}` "
        f"is still referenced at line(s) {', '.join(lines)}; update the call "
        f"sites too or Python raises NameError at runtime. "
        f"Do NOT stop here: make the second edit now, e.g. "
        f"edit_file(path, old_str=`{old_name}(`, new_str=`{new_name}(`) "
        f"for each stale call, then re-read the file. "
        f"Use grep to find all uses."
    )


def _locations(content: str, old: str) -> list[int]:
    """1-based line numbers of every exact occurrence."""
    locs: list[int] = []
    idx = 0
    while True:
        idx = content.find(old, idx)
        if idx < 0:
            return locs
        locs.append(content.count("\n", 0, idx) + 1)
        idx += max(1, len(old))


def _line_range(content: str, start: int, end: int) -> tuple[int, int]:
    return (content.count("\n", 0, start) + 1,
            max(content.count("\n", 0, start) + 1,
                content.count("\n", 0, end) + (0 if content.endswith("\n") else 1)))


def _ws_norm(line: str) -> str:
    return line.strip()


def _ws_candidates(content: str, old: str) -> list[tuple[int, int]]:
    """Char offsets of windows whose whitespace-normalized lines equal old's."""
    file_lines = content.splitlines(keepends=True)
    old_lines = old.splitlines()
    n = len(old_lines)
    if n == 0:
        return []
    # char offset of each line start
    offsets = []
    pos = 0
    for ln in file_lines:
        offsets.append(pos)
        pos += len(ln)
    want = [_ws_norm(ln) for ln in old_lines]
    out = []
    for i in range(len(file_lines) - n + 1):
        got = [_ws_norm(file_lines[i + j]) for j in range(n)]
        if got == want:
            out.append((offsets[i], offsets[i] + sum(len(file_lines[i + j])
                                                     for j in range(n))))
    return out


def _fuzzy_candidates(content: str, old: str) -> list[tuple[int, int, float]]:
    """(start, end, score) per window, best-first. Score on raw joined lines."""
    file_lines = content.splitlines(keepends=True)
    old_text = "\n".join(old.splitlines())
    n = len(old.splitlines())
    if n == 0 or not file_lines:
        return []
    offsets = []
    pos = 0
    for ln in file_lines:
        offsets.append(pos)
        pos += len(ln)
    scored = []
    for i in range(len(file_lines) - n + 1):
        window = "".join(file_lines[i:i + n])
        score = difflib.SequenceMatcher(
            None, "\n".join(window.splitlines()), old_text).ratio()
        scored.append((offsets[i],
                       offsets[i] + sum(len(file_lines[i + j]) for j in range(n)),
                       score))
    scored.sort(key=lambda t: t[2], reverse=True)
    return scored
