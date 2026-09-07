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


from specy_road.bundled_scripts.grind_session_args import parse_grind_session_args
from specy_road.bundled_scripts.grind_session_cleanup import run_session_cleanup
from specy_road.bundled_scripts.grind_session_implement import run_implement_hook
from specy_road.bundled_scripts.grind_session_limits import (
    resolve_implement_limits,
)
from specy_road.bundled_scripts.grind_session_events import (
    EXIT_GENERIC,
    EXIT_OK,
    EXIT_PICKUP_FAILED,
    EXIT_PRE_FINISH_FAILED,
    EventEmitter,
)
from specy_road.bundled_scripts.grind_session_in_flight import (
    handle_no_ready,
    own_in_flight_claims,
    prepare_resume,
)
from specy_road.bundled_scripts.session_plan import SessionPlan, compute_session_plan, session_plan_to_dict
from specy_road.bundled_scripts.session_plan_render import render_session_plan_text
from specy_road.bundled_scripts.roadmap_load import load_roadmap
from specy_road.registry_yaml import read_registry, registry_path
from specy_road.git_workflow_config import resolve_on_complete
from specy_road.runtime_paths import default_user_repo_root
from specy_road.bundled_scripts.repo_ops import current_branch


# ---------------------------------------------------------------------------
# State loading (read-only) — monkeypatched in tests
# ---------------------------------------------------------------------------


def gather_plan(repo_root: Path, under: str | None) -> tuple[list[dict], dict, SessionPlan]:
    nodes = load_roadmap(repo_root)["nodes"]
    reg = read_registry(registry_path(repo_root))
    return nodes, reg, compute_session_plan(nodes, reg, under=under)


# ---------------------------------------------------------------------------
# Subprocess + git helpers — monkeypatched in tests
# ---------------------------------------------------------------------------


#: In ``--json`` mode stdout carries JSONL and nothing else, so child output
#: (pickup banner, finish log, git) is redirected to stderr. Set per run by
#: :func:`run_session`; a module-level flag rather than an argument because the
#: two spawn helpers below are monkeypatched in tests by signature.
CHILD_STDOUT_TO_STDERR = False


def _spawn(cmd, *, cwd: Path, env: dict | None = None, shell: bool = False) -> int:
    """Run a child process, keeping our stdout clean when emitting JSONL."""
    if not CHILD_STDOUT_TO_STDERR:
        return subprocess.run(cmd, cwd=cwd, env=env, shell=shell).returncode
    sys.stderr.flush()
    try:
        fd = sys.stderr.fileno()
    except (AttributeError, ValueError, OSError):
        # No real file descriptor (pytest capture, embedded streams). Buffer
        # instead: streaming is lost, but stdout still never sees child output.
        proc = subprocess.run(
            cmd, cwd=cwd, env=env, shell=shell,
            stdout=subprocess.PIPE, text=True,
        )
        if proc.stdout:
            sys.stderr.write(proc.stdout)
            sys.stderr.flush()
        return proc.returncode
    return subprocess.run(cmd, cwd=cwd, env=env, shell=shell, stdout=fd).returncode


def _run_cli(repo_root: Path, cli_args: list[str]) -> int:
    return _spawn(
        [sys.executable, "-m", "specy_road.cli", *cli_args], cwd=repo_root
    )


def _run_shell(cmd: str, env: dict, repo_root: Path) -> int:
    return _spawn(cmd, cwd=repo_root, env=env, shell=True)


def _wait_for_signal(repo_root: Path, rel: str, timeout: float) -> bool:
    """manual mode: block until the ready-signal file appears (or Enter on a TTY)."""
    path = repo_root / rel
    if path.exists():
        path.unlink()
        return True
    if sys.stdin and sys.stdin.isatty():
        # input() writes its prompt to stdout, which in --json mode is the
        # event stream. Ask on stderr instead, or the first cycle puts a
        # non-JSON line into a pipe the caller is parsing.
        prompt = f"  Implement the task, then press Enter (or create {rel})... "
        try:
            if CHILD_STDOUT_TO_STDERR:
                print(prompt, file=sys.stderr, end="", flush=True)
                input()
            else:
                input(prompt)
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
    reg = read_registry(registry_path(repo_root))
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
        return run_implement_hook(
            args.implement_cmd,
            _hook_env(repo_root, **ctx),
            repo_root,
            emitter=emitter,
            node_id=ctx["node_id"],
            run_shell=_run_shell,
            limits=resolve_implement_limits(
                repo_root,
                max_limit_waits=args.max_limit_waits,
                max_limit_wait_hours=args.max_limit_wait_hours,
                limit_wait_grace_seconds=args.limit_wait_grace_seconds,
                max_empty_retries=args.max_empty_retries,
            ),
        )
    return 0 if _wait_for_signal(repo_root, args.ready_signal, args.signal_timeout) else 1


def _do_cycle(args, repo_root: Path, emitter: EventEmitter, nodes: list[dict],
              target_id: str) -> tuple[str | None, str | None, int | None]:
    by_id = {n["id"]: n for n in nodes}
    codename = (by_id.get(target_id, {}) or {}).get("codename") or ""
    rc = _run_cli(repo_root, _pickup_args(args, repo_root))
    if rc != 0:
        emitter.emit("hook_failed", phase="pickup", node_id=target_id, rc=rc)
        return None, None, EXIT_PICKUP_FAILED
    branch = current_branch(repo_root) or f"feature/rm-{codename}"
    node_id = _resolve_picked(repo_root, branch, target_id)
    return _implement_and_finish(
        args, repo_root, emitter, node_id, branch, event="picked"
    )


def _resume_cycle(args, repo_root: Path, emitter: EventEmitter, nodes: list[dict],
                  claim) -> tuple[str | None, str | None, int | None]:
    """Run a claim this worktree already holds through implement and finish.

    Pickup is skipped rather than repeated: the registry row is already on the
    integration branch and the branch already exists, so a second pickup would
    be the F-014 collision this resume path exists to avoid.
    """
    error = prepare_resume(
        repo_root, claim, nodes, on_complete=args.on_complete or "merge"
    )
    if error is not None:
        print(f"error: {error}", file=sys.stderr)
        emitter.emit("hook_failed", phase="resume", node_id=claim.node_id, rc=1)
        return None, None, EXIT_GENERIC
    return _implement_and_finish(
        args, repo_root, emitter, claim.node_id, claim.branch, event="resumed"
    )


def _implement_and_finish(args, repo_root: Path, emitter: EventEmitter, node_id: str,
                          branch: str, *, event: str) -> tuple[str | None, str | None, int | None]:
    ctx = {
        "node_id": node_id,
        "branch": branch,
        "brief": f"work/brief-{node_id}.md",
        "prompt": f"work/prompt-{node_id}.md",
    }
    emitter.emit(event, **ctx)
    rc = _implement(args, repo_root, emitter, ctx)
    if rc != 0:
        emitter.emit("hook_failed", phase="implement", node_id=node_id, rc=rc)
        return None, None, EXIT_GENERIC
    if args.pre_finish_cmd:
        emitter.emit("pre_finish", node_id=node_id)
        rc = _run_shell(args.pre_finish_cmd, _hook_env(repo_root, **ctx), repo_root)
        if rc != 0:
            emitter.emit("hook_failed", phase="pre_finish", node_id=node_id, rc=rc)
            return None, None, EXIT_PRE_FINISH_FAILED
    rc = _run_cli(repo_root, _finish_args(args, repo_root))
    if rc != 0:
        emitter.emit("hook_failed", phase="finish", node_id=node_id, rc=rc)
        return None, None, EXIT_GENERIC
    emitter.emit("finished", node_id=node_id)
    return node_id, branch, None


def _pin_loop_mode(repo_root: Path, args) -> str | None:
    """Resolve ``on_complete`` once and pin it on ``args``; return error text or None.

    ``pr`` never merges, so each cycle leaves its bookkeeping stranded on the
    feature branch and the next pickup — which syncs to the integration branch
    first — cannot see it. Since ``pr`` is also the fallback when nothing
    declares a mode, an unattended grind in a repo whose git-workflow.yaml omits
    ``on_complete`` silently degrades instead of failing.

    Pinning matters as much as rejecting: without an explicit ``--on-complete``,
    each cycle's ``do-next-available-task`` prompts on a TTY and writes the
    answer to the per-task session file, which ``finish-this-task`` prefers over
    the config. Answering ``pr`` once would put the loop back in the state this
    check exists to prevent. Writing the resolved mode back onto ``args`` makes
    both pass-through builders forward it, which also suppresses the prompt.
    """
    mode = resolve_on_complete(repo_root, cli=args.on_complete, session=None)
    if mode == "pr":
        return (
            "grind-session cannot run in 'pr' mode: it does not merge between "
            "cycles, so downstream dependencies stay blocked and the loop cannot "
            "continue. Pass --on-complete merge (or auto), or set 'on_complete' in "
            "roadmap/git-workflow.yaml. For one PR per leaf, use --plan plus "
            "individual do-next-available-task / finish-this-task runs."
        )
    args.on_complete = mode
    return None


def _emit_plan(emitter: EventEmitter, plan: SessionPlan) -> None:
    if emitter.as_json:
        emitter.emit("plan", **session_plan_to_dict(plan))
    else:
        emitter.emit("plan", text=render_session_plan_text(plan).rstrip())


def _run_loop(
    args, repo_root: Path, emitter: EventEmitter, finished_branches: list[str]
) -> tuple[int, bool]:
    """Drive cycles until a bound is hit. Returns (exit code, failed)."""
    for _cycle in range(max(1, args.max_cycles)):
        nodes, reg, plan = gather_plan(repo_root, args.under)
        if plan.ready:
            node_id, branch, terminal = _do_cycle(
                args, repo_root, emitter, nodes, plan.ready[0]
            )
        else:
            claims = (
                own_in_flight_claims(repo_root, reg, plan.active)
                if args.resume_in_flight
                else []
            )
            if not claims:
                return handle_no_ready(
                    emitter, plan, len(finished_branches),
                    repo_root=repo_root, reg=reg,
                ), False
            node_id, branch, terminal = _resume_cycle(
                args, repo_root, emitter, nodes, claims[0]
            )
        if terminal is not None:
            return terminal, True
        finished_branches.append(branch or "")
        if args.until and node_id == args.until:
            emitter.emit("stopped", reason="until_reached", node_id=node_id)
            return EXIT_OK, False
        if args.max_leaves and len(finished_branches) >= args.max_leaves:
            emitter.emit("stopped", reason="max_leaves", node_id=node_id)
            return EXIT_OK, False
    emitter.emit("stopped", reason="max_cycles")
    return EXIT_OK, False


def run_session(args) -> int:
    global CHILD_STDOUT_TO_STDERR
    repo_root = (args.repo_root or default_user_repo_root()).resolve()
    CHILD_STDOUT_TO_STDERR = bool(args.json)
    emitter = EventEmitter(as_json=args.json)
    if args.plan:
        _nodes, _reg, plan = gather_plan(repo_root, args.under)
        _emit_plan(emitter, plan)
        return EXIT_OK
    mode_error = _pin_loop_mode(repo_root, args)
    if mode_error is not None:
        print(f"error: {mode_error}", file=sys.stderr)
        return EXIT_GENERIC
    finished_branches: list[str] = []
    code, failed = _run_loop(args, repo_root, emitter, finished_branches)
    # Only when the loop got somewhere and stopped on its own terms. After a
    # failure the dev needs the feature branch exactly as it was left, and in
    # milestone-subtree mode finish lands on the rollup branch, not integration.
    if not failed and finished_branches and not args.milestone_subtree:
        run_session_cleanup(args, repo_root, emitter, finished_branches)
    return code


def main(argv: list[str] | None = None) -> None:
    args = parse_grind_session_args(argv)
    raise SystemExit(run_session(args))


if __name__ == "__main__":
    main()
