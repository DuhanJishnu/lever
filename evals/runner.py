"""Eval runner: (task, config, seed) -> JSONL results. Resumable + parallel.

Backends: `local` (subprocess, default until Docker Desktop is installed),
`docker` (isolated `python:3.12-slim`, `--network none`). `--backend auto`
uses Docker only if the daemon responds.

Real (keyed) B0 run: 30 tasks x 3 seeds. Dry-run (--dry-run, FakeProvider)
proves plumbing only — expect pass=0, it is NOT a result.
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

TASKS_DIR = ROOT / "evals" / "tasks"
CATEGORIES = {"bugfix", "feature", "refactor", "multi-file", "write-tests"}


# ---------- task loading / validation ----------

def load_task(task_dir: Path) -> dict:
    meta = json.loads((task_dir / "meta.json").read_text(encoding="utf-8"))
    assert meta.get("id") == task_dir.name, f"{task_dir}: meta.id mismatch"
    assert meta.get("category") in CATEGORIES, f"{task_dir}: bad category"
    assert (task_dir / "repo").is_dir(), f"{task_dir}: missing repo/"
    assert (task_dir / "task.md").exists(), f"{task_dir}: missing task.md"
    assert (task_dir / "hidden_tests").is_dir(), f"{task_dir}: missing hidden_tests/"
    assert (task_dir / "solution.patch").exists(), f"{task_dir}: missing solution.patch"
    meta["_dir"] = str(task_dir)
    return meta


def list_tasks(only: list[str] | None = None) -> list[dict]:
    tasks = [load_task(d) for d in sorted(TASKS_DIR.iterdir())
             if d.is_dir() and (d / "meta.json").exists()]
    if only:
        want = set(only)
        tasks = [t for t in tasks if t["id"] in want]
        missing = want - {t["id"] for t in tasks}
        assert not missing, f"unknown tasks: {sorted(missing)}"
    return tasks


def prepare_workspace(task: dict, dest: Path) -> Path:
    """Copy repo/ into dest. Hidden tests are staged ONLY at grading time
    (never visible to the agent during the run)."""
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(Path(task["_dir"]) / "repo", dest)
    return dest


def stage_hidden(task: dict, workdir: Path) -> None:
    """Copy hidden_tests/ into the workspace just before grading."""
    target = workdir / "hidden_tests"
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(Path(task["_dir"]) / "hidden_tests", target)
    (target / "conftest.py").write_text(
        "import sys\nfrom pathlib import Path\n"
        "sys.path.insert(0, str(Path(__file__).resolve().parent.parent))\n",
        encoding="utf-8",
    )


def resolve_cmd(test_cmd: str) -> list[str]:
    parts = test_cmd.split()
    if parts and parts[0] == "python":
        parts[0] = sys.executable
    return parts


# ---------- grading ----------

def grade_local(workdir: Path, test_cmd: str, timeout: int) -> tuple[bool, str]:
    try:
        proc = subprocess.run(
            resolve_cmd(test_cmd), check=False, cwd=workdir,
            capture_output=True, text=True, timeout=timeout,
        )
        tail = (proc.stdout + proc.stderr)[-2000:]
        return proc.returncode == 0, tail
    except subprocess.TimeoutExpired:
        return False, f"TIMEOUT after {timeout}s"


def grade_docker(workdir: Path, test_cmd: str, timeout: int) -> tuple[bool, str]:
    # Mount a COPY (never the original) so container writes can't leak out.
    # Image `lever-eval` (evals/Dockerfile) = python:3.12-slim + pytest.
    try:
        proc = subprocess.run(
            ["docker", "run", "--rm", "--network", "none",
             "-v", f"{workdir.resolve()}:/work", "-w", "/work",
             "lever-eval", "sh", "-c", test_cmd],
            check=False, capture_output=True, text=True, timeout=timeout + 60,
        )
        return proc.returncode == 0, (proc.stdout + proc.stderr)[-2000:]
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, f"docker backend failed: {e}"


def docker_available() -> bool:
    try:
        proc = subprocess.run(["docker", "info"], check=False,
                                  capture_output=True, timeout=10)
        return proc.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


# ---------- one run ----------

async def run_one(task: dict, config: dict, config_name: str, seed: int,
                  backend: str, work_root: Path, dry_run: bool,
                  provider_kind: str = "auto") -> dict:
    from lever.core.config import HarnessConfig
    from lever.core.loop import run_loop
    from lever.core.session import Session
    from lever.providers.cache import ResponseCache
    from lever.store.sqlite import EventStore

    cfg = HarnessConfig(**config)
    cfg.seed = seed
    t0 = time.time()
    run_dir = work_root / f"{task['id']}_{config_name}_s{seed}"
    prepare_workspace(task, run_dir)

    if provider_kind == "fake" or dry_run or (
            provider_kind == "auto" and not _has_key()):
        from lever.providers.fake import FakeProvider
        provider = FakeProvider.say_hi()
        provider_name = "fake"
    elif provider_kind == "local":
        # Local model (llama-server). Free; see docs/local_model.md.
        from lever.providers.local import LocalProvider
        provider = LocalProvider()
        provider_name = f"local:{provider.model}"
    else:
        from lever.providers.gemini import GeminiProvider
        provider = GeminiProvider()
        provider_name = provider.model

    store = EventStore(work_root / "events.db")
    session = Session(source=run_dir)
    ws = session.open(base_dir=work_root / "ws")
    # Agent works on the workspace copy; hidden tests were copied in too —
    # they sit in hidden_tests/ (never mentioned in the prompt) for grading only.
    task_text = (Path(task["_dir"]) / "task.md").read_text(encoding="utf-8")
    result = await run_loop(provider=provider, session=session, task=task_text,
                            config=cfg, store=store,
                            cache=ResponseCache(work_root / "cache.jsonl"),
                            seed=seed)
    events = store.read(session.session_id)
    store.close()

    # Grade: hidden tests are staged into the workspace ONLY now (grading time),
    # so the agent never sees them during the run.
    stage_hidden(task, ws)
    grade = grade_docker if backend == "docker" else grade_local
    passed, grade_tail = await asyncio.to_thread(
        grade, ws, task["test_cmd"], int(task.get("timeout", 120)),
    )
    wall = time.time() - t0
    return {
        "task": task["id"], "category": task["category"],
        "difficulty": task.get("difficulty", "medium"),
        "config": config_name, "seed": seed, "provider": provider_name,
        "backend": backend, "dry_run": dry_run,
        "pass": passed, "grade_tail": grade_tail,
        "stopped_by": result.stopped_by, "stop_reason": result.stop_reason,
        "nudges": sum(1 for e in events if e.type == "harness_nudge"
                      and e.data.get("kind") in ("nudge", "replan")),
        "steps": result.iterations,
        "tokens_in": sum(e.data.get("input_tokens", 0) for e in events
                         if e.type == "model_response"),
        "tokens_out": sum(e.data.get("output_tokens", 0) for e in events
                          if e.type == "model_response"),
        "tool_errors": sum(1 for e in events if e.type == "tool_result"
                           and str(e.data.get("result", "")).startswith(
                               ("Error", "Unknown tool"))),
        "edit_failures": sum(1 for e in events if e.type == "tool_result"
                             and e.data.get("name") == "edit_file"
                             and "Edit applied" not in str(e.data.get("result", ""))),
        "compactions": sum(1 for e in events if e.type == "context_compacted"),
        "context_sizes": [it.context_size for it in result.trace],
        "fell_for_trap": _trap_check(task, result.answer, ws),
        "diff_stat": session.get_diff(),
        "session_id": session.session_id,
        "wall_s": round(wall, 1),
        "cost_usd": None,  # set only with --rates (official pricing); tokens are truth
    }


def _has_key() -> bool:
    import os

    from dotenv import load_dotenv
    load_dotenv()
    return bool(os.getenv("GEMINI_API_KEY"))


def _trap_check(task: dict, answer: str, ws: Path) -> bool | None:
    """Did the trap pattern survive in the workspace code? Scans .py files only
    (never the prose answer — mentioning the trap while fixing it is fine)."""
    del answer  # explicit: prose must not trigger traps
    trap = task.get("trap")
    if not trap:
        return None
    for p in ws.rglob("*.py"):
        if "hidden_tests" in p.parts:
            continue
        try:
            if p.stat().st_size < 200_000 and trap in p.read_text(
                    encoding="utf-8", errors="replace"):
                return True
        except OSError:
            continue
    return False


# ---------- driver ----------

async def _main_async(args: argparse.Namespace, configs: dict) -> None:
    tasks = list_tasks(args.tasks)
    backend = args.backend
    if backend == "auto":
        backend = "docker" if docker_available() else "local"
    if backend == "docker" and not docker_available():
        print("docker daemon unreachable, falling back to local", file=sys.stderr)
        backend = "local"

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    done: set[tuple[str, str, int]] = set()
    if out.exists() and not args.redo:
        for line in out.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
                if r.get("error"):
                    continue  # error rows are retried, never resumed
                done.add((r["task"], r["config"], r["seed"]))
            except (json.JSONDecodeError, KeyError):
                continue

    sem = asyncio.Semaphore(args.jobs)
    work_root = Path(args.work_root)
    work_root.mkdir(parents=True, exist_ok=True)

    planned = [(t, cname, seed) for t in tasks for cname in configs
               for seed in range(args.seeds)
               if args.redo or (t["id"], cname, seed) not in done]
    if not args.dry_run and args.provider != "local":
        est = len(planned) * args.est_tokens_per_run
        print(f"LIVE RUN: {len(planned)} runs x ~{args.est_tokens_per_run} "
              f"tokens = ~{est:,} tokens (thinking billed).")
        if not args.yes:
            try:
                ok = input("Proceed? [y/N] ").strip().lower() == "y"
            except EOFError:
                ok = False
            if not ok:
                print("Aborted. Re-run with --yes to confirm.")
                return

    async def _guarded(task: dict, cname: str, cfg: dict, seed: int) -> None:
        async with sem:
            if (task["id"], cname, seed) in done:
                print(f"skip {task['id']} {cname} s{seed} (done)")
                return
            print(f"run {task['id']} {cname} s{seed} [{backend}] ...", flush=True)
            try:
                res = await run_one(task, copy.deepcopy(cfg), cname, seed,
                                    backend, work_root, args.dry_run,
                                    args.provider)
            except Exception as e:  # one bad run must never kill the matrix
                res = {
                    "task": task["id"], "category": task["category"],
                    "difficulty": task.get("difficulty", "medium"),
                    "config": cname, "seed": seed, "provider": "error",
                    "backend": backend, "dry_run": args.dry_run,
                    "pass": False, "error": f"{type(e).__name__}: {str(e)[:500]}",
                    "stopped_by": "error", "stop_reason": "", "nudges": 0,
                    "steps": 0, "tokens_in": 0,
                    "tokens_out": 0, "tool_errors": 0, "edit_failures": 0,
                    "compactions": 0, "context_sizes": [], "fell_for_trap": None,
                    "diff_stat": "", "session_id": "", "wall_s": 0.0,
                    "cost_usd": None,
                }
            await asyncio.to_thread(_append_result, out, res)
            print(f"  -> pass={res['pass']} stopped={res['stopped_by']} "
                  f"steps={res['steps']} {res['wall_s']}s", flush=True)

    await asyncio.gather(*[
        _guarded(t, cname, cfg, seed)
        for (t, cname, seed) in planned for cfg in [configs[cname]]
    ])


def _append_result(out: Path, res: dict) -> None:
    with out.open("a", encoding="utf-8") as f:
        f.write(json.dumps(res) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser(description="Lever eval runner")
    ap.add_argument("--tasks", nargs="*", default=None, help="task ids (default: all)")
    ap.add_argument("--config", default="evals/configs.json",
                    help="json {name: HarnessConfig-overrides}")
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--backend", default="auto", choices=["auto", "local", "docker"])
    ap.add_argument("--provider", default="auto",
                    choices=["auto", "fake", "gemini", "local"],
                    help="auto: fake for dry-run, else gemini. local: llama-server "
                         "(free, needs docs/local_model.md setup).")
    ap.add_argument("--jobs", type=int, default=2, help="parallel runs")
    ap.add_argument("--out", default="evals/results/r1.jsonl")
    ap.add_argument("--work-root", default="evals/work")
    ap.add_argument("--dry-run", action="store_true",
                    help="FakeProvider plumbing check (pass=0 expected)")
    ap.add_argument("--redo", action="store_true", help="ignore resumable progress")
    ap.add_argument("--live", action="store_true",
                    help="REQUIRED for real API runs. Without it, runs are "
                         "forced to --dry-run (spends $0).")
    ap.add_argument("--yes", action="store_true",
                    help="Skip the live-run cost confirmation prompt.")
    ap.add_argument("--est-tokens-per-run", type=int, default=25000,
                    help="Empirical tokens/run for cost estimates (measured "
                         "78-run matrix: ~21-26k with thinking on).")
    args = ap.parse_args()
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")  # repo .env wins regardless of cwd
    if not args.live:
        if not args.dry_run:
            print("NOT live: forcing --dry-run (pass --live to spend API budget).")
        args.dry_run = True
    with open(args.config, encoding="utf-8") as f:
        configs: dict[str, dict] = json.load(f)
    asyncio.run(_main_async(args, configs))


if __name__ == "__main__":
    main()
