"""Refuse a second claim in a checkout that already holds one (exit 6).

Pickup used to register, push and switch to a second leaf while the first was
still checked out, so one checkout silently owned two leaves. grind-session
already refused that case with exit 6; this applies the same test,
:func:`~specy_road.bundled_scripts.grind_session_in_flight.own_in_flight_claims`,
before pickup changes anything.

A claim is this checkout's when the registry names its branch *and* that branch
is present locally, minus branches another worktree has checked out: a
coordinator that hands leaves out with ``--worktree`` keeps every leaf's branch
in the same repository, and each of those belongs to its own worktree. A claim
whose branch is gone is not held here (another clone's, or a dead row for
``registry-prune``), so it never blocks a pickup.
"""

from __future__ import annotations

import sys
from pathlib import Path

from specy_road.bundled_scripts.grind_session_events import EXIT_IN_FLIGHT
from specy_road.bundled_scripts.grind_session_in_flight import InFlightClaim, own_in_flight_claims
from specy_road.git_subprocess import git_ok, local_branch_exists
from specy_road.registry_yaml import read_registry, registry_path
from specy_road.runtime_paths import git_root


def branches_in_other_worktrees(repo_root: Path) -> set[str]:
    """Local branches checked out in a worktree other than this one."""
    here = git_root(repo_root)
    ok, out = git_ok(["worktree", "list", "--porcelain"], repo_root)
    if not ok:
        return set()
    branches: set[str] = set()
    path: Path | None = None
    for line in out.splitlines():
        if line.startswith("worktree "):
            path = Path(line[len("worktree "):])
        elif line.startswith("branch refs/heads/") and path is not None and path.resolve() != here:
            branches.add(line[len("branch refs/heads/"):])
    return branches


def held_claims(repo_root: Path, reg: dict) -> list[InFlightClaim]:
    """Registry claims whose branch exists locally and no other worktree has checked out."""
    elsewhere = branches_in_other_worktrees(repo_root)
    node_ids = dict.fromkeys(e.get("node_id") for e in reg.get("entries") or [] if e.get("node_id"))

    def held_here(root: Path, branch: str) -> bool:
        # Looked up at call time so a test patching local_branch_exists here is honoured.
        return branch not in elsewhere and local_branch_exists(root, branch)

    return own_in_flight_claims(repo_root, reg, list(node_ids), branch_exists=held_here)


def refuse_second_claim(repo_root: Path, *, allow: bool) -> None:
    """Exit 6 naming the held claim(s), unless ``allow`` (``--allow-second-claim``)."""
    if allow:
        return
    claims = held_claims(repo_root, read_registry(registry_path(repo_root)))
    if not claims:
        return
    first = claims[0]
    lines = [
        f"error: this checkout already holds a claim on {first.node_id} ({first.branch}); "
        "pickup would register a second leaf here."
    ]
    if claims[1:]:
        lines.append(f"  also claimed here: {', '.join(c.node_id for c in claims[1:])}")
    lines.append(
        "  Finish it (specy-road finish-this-task) or release it "
        "(specy-road abort-task-pickup), then re-run; or pass --allow-second-claim "
        "to claim another leaf anyway."
    )
    print("\n".join(lines), file=sys.stderr)
    raise SystemExit(EXIT_IN_FLIGHT)
