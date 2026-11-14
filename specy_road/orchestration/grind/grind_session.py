#!/usr/bin/env python3
"""The ``specy-road grind-session`` loop: orchestrate the task cycle over many leaves.

Each cycle reuses the existing primitives (never edits the registry directly):

    do-next-available-task  ->  implement (manual signal | hook cmd)
                            ->  optional --pre-finish-cmd
                            ->  finish-this-task

Pickup runs the optional --baseline-cmd on the integration branch first.

Repeats until a stop condition (--until / --under / --max-leaves / no actionable
work). ``--plan`` prints a read-only dependency/wave report instead of running;
``--status`` a goal's leaves by state, a completion range and what waits on a person
(``grind_status``). ``--step pickup|finish`` runs one phase and exits (:func:`run_step`).

The command entry, ``specy_road.bundled_scripts.grind_session``, parses the arguments
(``grind_session_args``) and calls :func:`run_session`. See the exit-code and event contract in
``grind_session_events`` and the guide in ``docs/grind-session.md``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import asdict
from pathlib import Path

from specy_road.bundled_scripts.grind_session_args import (
    finish_args as _finish_args,
    # Re-exported: the loop module served the parser before the command entry moved out.
    parse_grind_session_args as parse_grind_session_args,
    pickup_args as _pickup_args,
)
from specy_road.orchestration.grind.grind_session_cleanup import run_session_cleanup
from specy_road.grind_status import run_status
from specy_road.orchestration.grind.grind_session_implement import (
    ImplementLimits,
    run_implement_hook,
)
from specy_road.orchestration.grind.grind_session_events import (
    EXIT_GENERIC,
    EXIT_OK,
    EXIT_PICKUP_FAILED,
    EXIT_PRE_FINISH_FAILED,
    EventEmitter,
)
from specy_road.orchestration.grind.grind_session_in_flight import (
    handle_no_ready,
    own_in_flight_claims,
    prepare_resume,
)
from specy_road.orchestration.grind.session_plan import SessionPlan, session_plan_to_dict
from specy_road.orchestration.grind.session_plan_git import gather_session_plan as gather_plan
from specy_road.orchestration.grind.session_plan_render import render_session_plan_text
from specy_road.registry_yaml import read_registry, registry_path
from specy_road.git_workflow_config import load_git_workflow_config, resolve_on_complete
from specy_road.runtime_paths import default_user_repo_root
from specy_road.repo_ops import current_branch
from specy_road.orchestration import recover_stalled


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
    return _spawn([sys.executable, "-m", "specy_road.cli", *cli_args], cwd=repo_root)


def _run_shell(cmd: str, env: dict, repo_root: Path) -> int:
    return _spawn(cmd, cwd=repo_root, env=env, shell=True)


#: Seconds between stalled-worker recoveries while manual mode waits for its signal.
RECOVER_EVERY = 60.0


def _recover_stalled(repo_root: Path, emitter: EventEmitter | None = None) -> None:
    """``worker recover`` for each stalled worker.

    One ``worker_recovered``, ``worker_needs_person`` or ``worker_recover_refused`` event each.
    Never raises: recovery must not stop the session.
    """
    # JSON mode is when children go to stderr.
    emitter = emitter or EventEmitter(as_json=CHILD_STDOUT_TO_STDERR)
    try:
        results = recover_stalled(repo_root)
    except Exception as e:  # noqa: BLE001 — an unreadable workers directory is reported, not fatal
        results = [{"worker_id": None, "node_id": None, "outcome": "refused", "detail": str(e)}]
    for r in results:
        event = {"recovered": "worker_recovered", "needs_person": "worker_needs_person"}.get(
            r["outcome"], "worker_recover_refused")
        emitter.emit(event, node_id=r["node_id"], worker_id=r["worker_id"], detail=r["detail"])


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
        if waited and waited % RECOVER_EVERY == 0:
            _recover_stalled(repo_root)   # a stalled worker does not wait for a person
        time.sleep(interval)
        waited += interval


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
# Implement bounds
# ---------------------------------------------------------------------------


#: ``git-workflow.yaml`` key -> :class:`ImplementLimits` field.
_YAML_LIMIT_KEYS = {
    "grind_session_max_limit_waits": "max_resumes",
    "grind_session_max_limit_wait_hours": "max_wait_seconds",
    "grind_session_limit_wait_grace_seconds": "grace_seconds",
    "grind_session_max_empty_retries": "max_empty_retries",
}


def _limits_from_git_workflow(repo_root: Path) -> dict[str, int]:
    """Bounds set in ``roadmap/git-workflow.yaml``, if any.

    An unreadable or schema-invalid file yields nothing, exactly as the
    boolean settings behave. grind-session cannot reach this step with a broken
    file anyway: ``on_complete`` resolution reads the same file first and
    refuses to start the loop.
    """
    data, err = load_git_workflow_config(repo_root)
    if err or not data:
        return {}
    out: dict[str, int] = {}
    for key, field in _YAML_LIMIT_KEYS.items():
        value = data.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        out[field] = int(value * 3600) if field == "max_wait_seconds" else int(value)
    return out


def resolve_implement_limits(
    repo_root: Path,
    *,
    max_limit_waits: int | None = None,
    max_limit_wait_hours: float | None = None,
    limit_wait_grace_seconds: int | None = None,
    max_empty_retries: int | None = None,
) -> ImplementLimits:
    """Bounds for the implement step: CLI flag > git-workflow.yaml > default.

    Hours in, seconds out. A person quotes a reset in hours and so does the
    loop's own refusal message, while every comparison inside the loop is in
    seconds. Testable without building an argparse namespace.
    """
    values: dict[str, int] = asdict(ImplementLimits.defaults())
    values.update(_limits_from_git_workflow(repo_root))
    cli = {
        "max_resumes": max_limit_waits,
        "max_wait_seconds": (
            None if max_limit_wait_hours is None else int(max_limit_wait_hours * 3600)
        ),
        "grace_seconds": limit_wait_grace_seconds,
        "max_empty_retries": max_empty_retries,
    }
    values.update({k: v for k, v in cli.items() if v is not None})
    return ImplementLimits(**{k: max(0, int(v)) for k, v in values.items()})


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
    collide with that claim, which is what this resume path exists to avoid.
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


def _ctx(node_id: str, branch: str) -> dict:
    """The leaf a cycle works on, and the pickup artifacts the hooks read."""
    return {
        "node_id": node_id,
        "branch": branch,
        "brief": f"work/brief-{node_id}.md",
        "prompt": f"work/prompt-{node_id}.md",
    }


def _implement_and_finish(args, repo_root: Path, emitter: EventEmitter, node_id: str,
                          branch: str, *, event: str) -> tuple[str | None, str | None, int | None]:
    ctx = _ctx(node_id, branch)
    emitter.emit(event, **ctx)
    rc = _implement(args, repo_root, emitter, ctx)
    if rc != 0:
        emitter.emit("hook_failed", phase="implement", node_id=node_id, rc=rc)
        return None, None, EXIT_GENERIC
    terminal = _finish_phase(args, repo_root, emitter, ctx)
    if terminal is not None:
        return None, None, terminal
    return node_id, branch, None


def _finish_phase(args, repo_root: Path, emitter: EventEmitter, ctx: dict) -> int | None:
    """Optional pre-finish hook, then ``finish-this-task``. Exit code, or None."""
    node_id = ctx["node_id"]
    if args.pre_finish_cmd:
        emitter.emit("pre_finish", node_id=node_id)
        rc = _run_shell(args.pre_finish_cmd, _hook_env(repo_root, **ctx), repo_root)
        if rc != 0:
            emitter.emit("hook_failed", phase="pre_finish", node_id=node_id, rc=rc)
            return EXIT_PRE_FINISH_FAILED
    rc = _run_cli(repo_root, _finish_args(args, repo_root))
    if rc != 0:
        emitter.emit("hook_failed", phase="finish", node_id=node_id, rc=rc)
        return EXIT_GENERIC
    emitter.emit("finished", node_id=node_id)
    return None


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


def _emit_plan(
    emitter: EventEmitter,
    plan: SessionPlan,
    repo_root: Path,
    nodes: list[dict],
    fields: list[str] | None = None,
) -> None:
    if emitter.as_json and fields:   # exactly the selected keys, no event/ts envelope
        print(json.dumps(session_plan_to_dict(plan, fields)), flush=True)
    elif emitter.as_json:
        emitter.emit("plan", **session_plan_to_dict(plan))
    else:
        text = render_session_plan_text(plan, repo_root=repo_root, nodes=nodes)
        emitter.emit("plan", text=text.rstrip())


def _run_loop(
    args, repo_root: Path, emitter: EventEmitter, finished_branches: list[str]
) -> tuple[int, bool]:
    """Drive cycles until a bound is hit. Returns (exit code, failed)."""
    for _cycle in range(max(1, args.max_cycles)):
        # Each cycle: a stalled worker does not wait for a person.
        _recover_stalled(repo_root, emitter)
        nodes, reg, plan = gather_plan(
            repo_root, args.under, allow_unauthored=args.allow_unauthored,
            prefer_agentic=args.prefer_agentic,
        )
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
    if args.status:   # read-only: no loop-mode pin, no git writes
        return run_status(repo_root, args)
    if args.plan:
        _nodes, _reg, plan = gather_plan(
            repo_root, args.under, allow_unauthored=args.allow_unauthored,
            prefer_agentic=args.prefer_agentic,
        )
        _emit_plan(emitter, plan, repo_root, _nodes, args.fields)
        return EXIT_OK
    mode_error = _pin_loop_mode(repo_root, args)
    if mode_error is not None:
        print(f"error: {mode_error}", file=sys.stderr)
        return EXIT_GENERIC
    # Inherited by every child. Pickup's footer advertises this loop, which is
    # noise once you are already inside it.
    os.environ["SPECY_ROAD_GRIND_SESSION"] = "1"
    if args.step:
        return run_step(args, repo_root, emitter)
    finished_branches: list[str] = []
    code, failed = _run_loop(args, repo_root, emitter, finished_branches)
    # Only when the loop got somewhere and stopped on its own terms. After a
    # failure the dev needs the feature branch exactly as it was left, and in
    # milestone-subtree mode finish lands on the rollup branch, not integration.
    if not failed and finished_branches and not args.milestone_subtree:
        run_session_cleanup(args, repo_root, emitter, finished_branches)
    return code


# ---------------------------------------------------------------------------
# --step pickup|finish: one phase per run, for an agent
# ---------------------------------------------------------------------------
#
# The loop owns a process for the whole session and calls an implement hook
# between pickup and finish. An IDE agent session cannot be that hook: it *is*
# the implementer, and it cannot sit inside a blocking process. Step mode hands
# the loop to the agent instead. It runs pickup, exits so the agent can
# implement (ideally in a fresh sub-agent), and is called again to finish.
# Usage limits are then the agent harness's to wait out, not ours.


def run_step(args, repo_root: Path, emitter: EventEmitter) -> int:
    """Run the one phase ``args.step`` names. Its exit code."""
    global CHILD_STDOUT_TO_STDERR
    # A caller may reach this without run_session, which sets the flag. Without
    # it, pickup's banner lands on stdout in the middle of the JSONL.
    CHILD_STDOUT_TO_STDERR = bool(args.json)
    if args.step == "pickup":
        return _step_pickup(args, repo_root, emitter)
    return _step_finish(args, repo_root, emitter)


def _step_pickup(args, repo_root: Path, emitter: EventEmitter) -> int:
    """Resume this clone's open claim, else pick the next ready leaf.

    The claim comes first, the reverse of the loop. The caller is usually the
    same session that held it before a usage limit or a crash, and a second
    claim on top of an unfinished one is exactly what ``--step finish`` could
    not tell apart. Ownership still needs a registry row *and* a local branch.
    """
    nodes, reg, plan = gather_plan(
        repo_root, args.under, allow_unauthored=args.allow_unauthored,
        prefer_agentic=args.prefer_agentic,
    )
    claims = own_in_flight_claims(repo_root, reg, plan.active)
    if claims:
        claim = claims[0]
        error = prepare_resume(
            repo_root, claim, nodes, on_complete=args.on_complete or "merge"
        )
        if error is not None:
            print(f"error: {error}", file=sys.stderr)
            emitter.emit("hook_failed", phase="resume", node_id=claim.node_id, rc=1)
            return EXIT_GENERIC
        emitter.emit("resumed", **_ctx(claim.node_id, claim.branch))
        return EXIT_OK
    if not plan.ready:
        return handle_no_ready(emitter, plan, 0, repo_root=repo_root, reg=reg)
    target = plan.ready[0]
    codename = next(
        (n.get("codename") for n in nodes if n.get("id") == target), None
    ) or ""
    rc = _run_cli(repo_root, _pickup_args(args, repo_root))
    if rc != 0:
        emitter.emit("hook_failed", phase="pickup", node_id=target, rc=rc)
        return EXIT_PICKUP_FAILED
    branch = current_branch(repo_root) or f"feature/rm-{codename}"
    node_id = _resolve_picked(repo_root, branch, target)
    emitter.emit("picked", **_ctx(node_id, branch))
    return EXIT_OK


def _step_finish(args, repo_root: Path, emitter: EventEmitter) -> int:
    """Pre-finish hook and ``finish-this-task`` for the checked-out claim.

    The current branch decides which claim, so several open claims are never
    ambiguous. Anything else stops before the pre-finish hook runs.
    """
    branch = current_branch(repo_root) or ""
    node_id = (
        _resolve_picked(repo_root, branch, "")
        if branch.startswith("feature/rm-")
        else ""
    )
    if not node_id:
        print(
            f"error: grind-session --step finish needs a claimed feature/rm-* "
            f"branch checked out, but HEAD is on {branch or 'no branch'!r}. "
            "Run `specy-road grind-session --step pickup`, which checks out "
            "this clone's open claim, then retry.",
            file=sys.stderr,
        )
        emitter.emit("hook_failed", phase="locate_claim", branch=branch, rc=1)
        return EXIT_GENERIC
    terminal = _finish_phase(args, repo_root, emitter, _ctx(node_id, branch))
    if terminal is not None:
        return terminal
    if args.until and node_id == args.until:
        emitter.emit("stopped", reason="until_reached", node_id=node_id)
    return EXIT_OK
