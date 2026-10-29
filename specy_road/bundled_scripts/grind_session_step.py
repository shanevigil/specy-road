"""``grind-session --step pickup|finish`` — one phase per run, for an agent.

The loop in ``grind_session`` owns a process for the whole session and calls
an implement hook between pickup and finish. An IDE agent session cannot be
that hook: it *is* the implementer, and it cannot sit inside a blocking
process. Step mode hands the loop to the agent instead. It runs pickup, exits
so the agent can implement (ideally in a fresh sub-agent), and is called again
to finish. Usage limits are then the agent harness's to wait out, not ours.

Every helper is reached through the ``grind_session`` module object, so tests
that ``monkeypatch.setattr(gs, ...)`` drive step mode exactly as they drive
the loop.
"""

from __future__ import annotations

import sys
from pathlib import Path

from specy_road.bundled_scripts import grind_session as gs
from specy_road.bundled_scripts.grind_session_events import (
    EXIT_GENERIC,
    EXIT_OK,
    EXIT_PICKUP_FAILED,
    EventEmitter,
)
from specy_road.bundled_scripts.grind_session_in_flight import (
    handle_no_ready,
    own_in_flight_claims,
    prepare_resume,
)


def _ctx(node_id: str, branch: str) -> dict:
    return {
        "node_id": node_id,
        "branch": branch,
        "brief": f"work/brief-{node_id}.md",
        "prompt": f"work/prompt-{node_id}.md",
    }


def run_step(args, repo_root: Path, emitter: EventEmitter) -> int:
    # ``specy-road grind-session`` runs grind_session as ``__main__``, so the
    # ``gs`` imported above is a second copy whose flag run_session never set.
    # Without this, pickup's banner lands on stdout in the middle of the JSONL.
    gs.CHILD_STDOUT_TO_STDERR = bool(args.json)
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
    nodes, reg, plan = gs.gather_plan(
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
    rc = gs._run_cli(repo_root, gs._pickup_args(args, repo_root))
    if rc != 0:
        emitter.emit("hook_failed", phase="pickup", node_id=target, rc=rc)
        return EXIT_PICKUP_FAILED
    branch = gs.current_branch(repo_root) or f"feature/rm-{codename}"
    node_id = gs._resolve_picked(repo_root, branch, target)
    emitter.emit("picked", **_ctx(node_id, branch))
    return EXIT_OK


def _step_finish(args, repo_root: Path, emitter: EventEmitter) -> int:
    """Pre-finish hook and ``finish-this-task`` for the checked-out claim.

    The current branch decides which claim, so several open claims are never
    ambiguous. Anything else stops before the pre-finish hook runs.
    """
    branch = gs.current_branch(repo_root) or ""
    node_id = (
        gs._resolve_picked(repo_root, branch, "")
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
    terminal = gs._finish_phase(args, repo_root, emitter, _ctx(node_id, branch))
    if terminal is not None:
        return terminal
    if args.until and node_id == args.until:
        emitter.emit("stopped", reason="until_reached", node_id=node_id)
    return EXIT_OK
