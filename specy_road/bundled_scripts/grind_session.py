#!/usr/bin/env python3
"""``specy-road grind-session`` — orchestrate the task loop over many leaves.

Each cycle reuses the existing primitives (never edits the registry directly):

    do-next-available-task  ->  implement (manual signal | hook cmd)
                            ->  optional --pre-finish-cmd
                            ->  finish-this-task

Repeats until a stop condition (--until / --under / --max-leaves / no actionable
work). ``--plan`` prints a read-only dependency/wave report instead of running.

See exit-code and event contract in ``grind_session_events`` and the guide in
``docs/grind-session.md``.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import yaml

from grind_session_args import parse_grind_session_args
from grind_session_events import (
    EXIT_BLOCKED,
    EXIT_GENERIC,
    EXIT_NO_LEAVES,
    EXIT_OK,
    EXIT_PICKUP_FAILED,
    EXIT_PRE_FINISH_FAILED,
    EventEmitter,
)
from session_plan import SessionPlan, compute_session_plan, session_plan_to_dict
from session_plan_render import render_session_plan_text
from roadmap_load import load_roadmap
from specy_road.runtime_paths import default_user_repo_root


# ---------------------------------------------------------------------------
# State loading (read-only) — monkeypatched in tests
# ---------------------------------------------------------------------------


def _load_registry(repo_root: Path) -> dict:
    path = repo_root / "roadmap" / "registry.yaml"
    if not path.is_file():
        return {"version": 1, "entries": []}
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {"version": 1, "entries": []}


def gather_plan(repo_root: Path, under: str | None) -> tuple[list[dict], dict, SessionPlan]:
    nodes = load_roadmap(repo_root)["nodes"]
    reg = _load_registry(repo_root)
    return nodes, reg, compute_session_plan(nodes, reg, under=under)


# ---------------------------------------------------------------------------
# Subprocess + git helpers — monkeypatched in tests
# ---------------------------------------------------------------------------


def _run_cli(repo_root: Path, cli_args: list[str]) -> int:
    proc = subprocess.run(
        [sys.executable, "-m", "specy_road.cli", *cli_args], cwd=repo_root
    )
    return proc.returncode


def _run_shell(cmd: str, env: dict, repo_root: Path) -> int:
    proc = subprocess.run(cmd, shell=True, cwd=repo_root, env=env)
    return proc.returncode


def _current_branch(repo_root: Path) -> str:
    r = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=repo_root, capture_output=True, text=True, check=False,
    )
    return (r.stdout or "").strip()


def _wait_for_signal(repo_root: Path, rel: str, timeout: float) -> bool:
    """manual mode: block until the ready-signal file appears (or Enter on a TTY)."""
    path = repo_root / rel
    if path.exists():
        path.unlink()
        return True
    if sys.stdin and sys.stdin.isatty():
        try:
            input(f"  Implement the task, then press Enter (or create {rel})... ")
        except EOFError:
            pass
        if path.exists():
            path.unlink()
        return True
    waited = 0.0
    interval = 1.0
    while True:
        if path.exists():
            path.unlink()
            return True
        if timeout and waited >= timeout:
            return False
        time.sleep(interval)
        waited += interval


# ---------------------------------------------------------------------------
# Argument builders for pass-through
# ---------------------------------------------------------------------------


def _pickup_args(args, repo_root: Path) -> list[str]:
    out = ["do-next-available-task", "--repo-root", str(repo_root)]
    if args.base:
        out += ["--base", args.base]
    if args.remote:
        out += ["--remote", args.remote]
    if args.on_complete:
        out += ["--on-complete", args.on_complete]
    if args.no_ci_skip_in_message:
        out.append("--no-ci-skip-in-message")
    if args.milestone_subtree:
        out.append("--milestone-subtree")
    elif args.under:
        out += ["--under", args.under]
    return out


def _finish_args(args, repo_root: Path) -> list[str]:
    out = ["finish-this-task", "--repo-root", str(repo_root)]
    if args.on_complete:
        out += ["--on-complete", args.on_complete]
    if args.remote:
        out += ["--remote", args.remote]
    if args.push:
        out.append("--push")
    return out


def _hook_env(repo_root: Path, node_id: str, branch: str, brief: str, prompt: str) -> dict:
    env = os.environ.copy()
    env.update({
        "SPECY_ROAD_NODE_ID": node_id,
        "SPECY_ROAD_BRANCH": branch,
        "SPECY_ROAD_BRIEF": brief,
        "SPECY_ROAD_PROMPT": prompt,
        "SPECY_ROAD_REPO_ROOT": str(repo_root),
    })
    return env


def _resolve_picked(repo_root: Path, branch: str, fallback_id: str) -> str:
    """Map the post-pickup feature branch back to its claimed node id."""
    if not branch.startswith("feature/rm-"):
        return fallback_id
    codename = branch[len("feature/rm-"):]
    reg = _load_registry(repo_root)
    for e in reg.get("entries") or []:
        if e.get("codename") == codename and e.get("node_id"):
            return e["node_id"]
    return fallback_id


# ---------------------------------------------------------------------------
# Cycle + loop
# ---------------------------------------------------------------------------


def _implement(args, repo_root: Path, emitter: EventEmitter, ctx: dict) -> int:
    emitter.emit("implementing", node_id=ctx["node_id"], mode=args.implement_mode)
    if args.implement_mode == "hook":
        return _run_shell(args.implement_cmd, _hook_env(repo_root, **ctx), repo_root)
    return 0 if _wait_for_signal(repo_root, args.ready_signal, args.signal_timeout) else 1


def _do_cycle(args, repo_root: Path, emitter: EventEmitter, nodes: list[dict],
              target_id: str) -> tuple[str | None, int | None]:
    by_id = {n["id"]: n for n in nodes}
    codename = (by_id.get(target_id, {}) or {}).get("codename") or ""
    rc = _run_cli(repo_root, _pickup_args(args, repo_root))
    if rc != 0:
        emitter.emit("hook_failed", phase="pickup", node_id=target_id, rc=rc)
        return None, EXIT_PICKUP_FAILED
    branch = _current_branch(repo_root) or f"feature/rm-{codename}"
    node_id = _resolve_picked(repo_root, branch, target_id)
    ctx = {
        "node_id": node_id,
        "branch": branch,
        "brief": f"work/brief-{node_id}.md",
        "prompt": f"work/prompt-{node_id}.md",
    }
    emitter.emit("picked", **ctx)
    rc = _implement(args, repo_root, emitter, ctx)
    if rc != 0:
        emitter.emit("hook_failed", phase="implement", node_id=node_id, rc=rc)
        return None, EXIT_GENERIC
    if args.pre_finish_cmd:
        emitter.emit("pre_finish", node_id=node_id)
        rc = _run_shell(args.pre_finish_cmd, _hook_env(repo_root, **ctx), repo_root)
        if rc != 0:
            emitter.emit("hook_failed", phase="pre_finish", node_id=node_id, rc=rc)
            return None, EXIT_PRE_FINISH_FAILED
    rc = _run_cli(repo_root, _finish_args(args, repo_root))
    if rc != 0:
        emitter.emit("hook_failed", phase="finish", node_id=node_id, rc=rc)
        return None, EXIT_GENERIC
    emitter.emit("finished", node_id=node_id)
    return node_id, None


def _handle_no_ready(emitter: EventEmitter, plan: SessionPlan, finished: int) -> int:
    if plan.blocked:
        b = plan.blocked[0]
        emitter.emit("blocked", reason=b.reason, waiting_on=b.waiting_on,
                     count=len(plan.blocked), node_id=b.node_id)
        return EXIT_BLOCKED
    if finished > 0:
        emitter.emit("stopped", reason="no_work")
        return EXIT_OK
    emitter.emit("stopped", reason="no_actionable_leaves")
    return EXIT_NO_LEAVES


def _emit_plan(emitter: EventEmitter, plan: SessionPlan) -> None:
    if emitter.as_json:
        emitter.emit("plan", **session_plan_to_dict(plan))
    else:
        emitter.emit("plan", text=render_session_plan_text(plan).rstrip())


def run_session(args) -> int:
    repo_root = (args.repo_root or default_user_repo_root()).resolve()
    emitter = EventEmitter(as_json=args.json)
    if args.plan:
        _nodes, _reg, plan = gather_plan(repo_root, args.under)
        _emit_plan(emitter, plan)
        return EXIT_OK
    finished = 0
    for _cycle in range(max(1, args.max_cycles)):
        nodes, _reg, plan = gather_plan(repo_root, args.under)
        if not plan.ready:
            return _handle_no_ready(emitter, plan, finished)
        node_id, terminal = _do_cycle(args, repo_root, emitter, nodes, plan.ready[0])
        if terminal is not None:
            return terminal
        finished += 1
        if args.until and node_id == args.until:
            emitter.emit("stopped", reason="until_reached", node_id=node_id)
            return EXIT_OK
        if args.max_leaves and finished >= args.max_leaves:
            emitter.emit("stopped", reason="max_leaves", node_id=node_id)
            return EXIT_OK
    emitter.emit("stopped", reason="max_cycles")
    return EXIT_OK


def main(argv: list[str] | None = None) -> None:
    args = parse_grind_session_args(argv)
    raise SystemExit(run_session(args))


if __name__ == "__main__":
    main()
