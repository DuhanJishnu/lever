"""B3 repo map: structure-first codebase orientation for the model.

Pipeline: scan (.py via stdlib `ast` — exact, zero new deps) → file graph
(A imports/uses a symbol defined in B) → personalized PageRank → compact
render under a token budget. Non-Python files are listed, not parsed
(tree-sitter for polyglot parsing is explicit future work).

Design notes:
- `build_repomap()` is pure (root + task + touched in, text out) so the loop
  can rebuild it cheaply after edits that add/move definitions.
- Personalization (task mentions ×3, touched files ×2) encodes "where the
  human is looking" into the ranking — Lost-in-the-Middle says placement
  matters, so rank order IS the placement.
"""

from __future__ import annotations

import ast
from collections.abc import Collection
from pathlib import Path
from typing import Any

# Map budget: compact enough to pin permanently, rich enough to orient.
# 1500 tokens ≈ 6000 chars at our standard chars//4 estimate.
REPOMAP_BUDGET_TOKENS = 1500
CHARS_PER_TOKEN = 4

SKIP_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache",
             "node_modules", "hidden_tests"}


def scan_file(path: Path) -> dict[str, Any]:
    """Extract definitions (kind, name, line, signature) + referenced names."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except (SyntaxError, ValueError):
        return {"defs": [], "refs": set(), "ok": False}
    defs: list[tuple[str, str, int, str]] = []
    refs: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            defs.append(("class", node.name, node.lineno, ""))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            defs.append(("def", node.name, node.lineno, _sig(node.args)))
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            refs.add(node.id)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                refs.add(node.module.split(".")[0])
            refs.update(a.asname or a.name for a in node.names if a.name != "*")
    return {"defs": defs, "refs": refs, "ok": True}


def _sig(args: ast.arguments) -> str:
    try:
        return "(" + ast.unparse(args) + ")"
    except (ValueError, SyntaxError):
        names = [a.arg for a in args.args]
        if args.vararg:
            names.append("*" + args.vararg.arg)
        if args.kwarg:
            names.append("**" + args.kwarg.arg)
        return "(" + ", ".join(names) + ")"


def collect_files(root: Path) -> list[Path]:
    root = Path(root)
    return sorted(
        p for p in root.rglob("*.py")
        if p.is_file() and not any(d in p.parts for d in SKIP_DIRS)
    )


def build_graph(files: list[Path], root: Path) -> dict[str, list[str]]:
    """File -> files it depends on (references a symbol they define)."""
    infos = {str(f.relative_to(root)): scan_file(f) for f in files}
    defines: dict[str, set[str]] = {}
    for rel, info in infos.items():
        for _kind, name, _ln, _sig in info["defs"]:
            defines.setdefault(name, set()).add(rel)
    edges: dict[str, list[str]] = {rel: [] for rel in infos}
    stems = {rel: Path(rel).stem for rel in infos}
    for rel, info in infos.items():
        targets: set[str] = set()
        for ref in info["refs"]:
            for owner in defines.get(ref, set()):
                if owner != rel:
                    targets.add(owner)
            # `from x import ...` / `import x`: ref names the module stem
            for other, stem in stems.items():
                if other != rel and (ref == stem or ref.split(".")[0] == stem):
                    targets.add(other)
        edges[rel] = sorted(targets)
    return edges


def pagerank(nodes: list[str], edges: dict[str, list[str]],
             personal: dict[str, float], damping: float = 0.85,
             iters: int = 50) -> dict[str, float]:
    total_p = sum(personal.get(v, 1.0) for v in nodes) or 1.0
    base = {v: personal.get(v, 1.0) / total_p for v in nodes}
    rank = dict(base)
    out_n = {v: max(1, len(edges.get(v, []))) for v in nodes}
    for _ in range(iters):
        dangling = sum(rank[v] for v in nodes if not edges.get(v))
        new = {}
        for v in nodes:
            inbound = sum(rank[u] / out_n[u] for u in nodes
                          if v in edges.get(u, []))
            new[v] = ((1.0 - damping) * base[v]
                      + damping * (inbound + dangling / len(nodes)))
        rank = new
    return rank


def build_repomap(root: Path | str, task: str = "",
                  touched: Collection[str] = (),
                  budget_tokens: int = REPOMAP_BUDGET_TOKENS) -> str:
    """Ranked `file -> signatures` text fitting budget_tokens (chars//4)."""
    root = Path(root)
    files = collect_files(root)
    if not files:
        return "(empty workspace)"
    rels = [str(f.relative_to(root)) for f in files]
    infos = {str(f.relative_to(root)): scan_file(f) for f in files}
    task_low = task.lower()
    touched_set = {str(t).replace("\\", "/") for t in touched}
    personal = {}
    for rel in rels:
        w = 1.0
        stem = Path(rel).stem.lower()
        if stem and stem in task_low:
            w *= 3.0
        if rel in touched_set:
            w *= 2.0
        personal[rel] = w
    ranks = pagerank(rels, build_graph(files, root), personal)
    budget_chars = budget_tokens * CHARS_PER_TOKEN
    lines = [f"Repo map ({len(rels)} python files; higher first):"]
    used = len(lines[0])
    for rel in sorted(rels, key=lambda r: ranks[r], reverse=True):
        entry = [f"{rel} [{ranks[rel]:.2f}]"]
        for kind, name, lineno, sig in infos[rel]["defs"][:12]:
            entry.append(f"  {kind} {name}{sig}  # L{lineno}")
        if len(infos[rel]["defs"]) > 12:
            entry.append(f"  ... +{len(infos[rel]['defs']) - 12} more")
        block = "\n".join(entry)
        if used + len(block) + 1 > budget_chars:
            lines.append(f"... +{len(rels) - len(lines) + 1} more files (budget)")
            break
        lines.append(block)
        used += len(block) + 1
    return "\n".join(lines)
