"""Tell an operator's *own* in-flight claim apart from a dependency block.

``SessionPlan.active`` is the union of two populations: nodes with a row in
``roadmap/registry.yaml``, and nodes merely marked *In Progress* in the graph.
In the multi-lane setup the toolkit recommends — separate clones, one roadmap
phase each, one integration branch — most of those belong to **other clones**,
because every lane pushes its claim to the shared integration branch before it
branches. So ``active`` on its own cannot answer "is this mine?".

A claim counts as this worktree's only when the registry names a branch *and*
that branch is present locally. Both halves are load-bearing: the registry row
alone is visible to every lane, and a local branch alone (one left behind by
hand, say) is not a claim. Getting this wrong in the permissive direction would
put two lanes on one leaf against a single integration branch, which is a fresh
instance of the corruption resolved in ``finish_land_integration``.

The narrowness is deliberate in the other direction too. A claim this worktree
cannot prove is its own stays out of the list, and the caller falls through to
its ordinary blocked/no-work reporting: a missed resume is an inconvenience,
where a wrong resume is two implementers writing the same node.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from specy_road.bundled_scripts.do_next_finished_unmerged import node_complete_on_ref
from specy_road.bundled_scripts.grind_session_events import (
    EXIT_BLOCKED,
    EXIT_IN_FLIGHT,
    EXIT_NO_LEAVES,
    EXIT_OK,
)
from specy_road.git_subprocess import git_code, local_branch_exists


@dataclass(frozen=True)
class InFlightClaim:
    """A registered claim whose feature branch exists in this worktree."""

    node_id: str
    codename: str
    branch: str


def own_in_flight_claims(
    repo_root: Path,
    reg: dict,
    active_ids,
    *,
    branch_exists=None,
) -> list[InFlightClaim]:
    """Claims among ``active_ids`` that this worktree can prove are its own.

    Ordered by ``active_ids`` so the caller reports the leaf the plan listed
    first, rather than whatever order the registry happens to be in.

    ``branch_exists`` falls back to the module-level probe **at call time**
    rather than binding it as a default, which would freeze the function at
    import and silently ignore anyone who patches it.
    """
    check = branch_exists or local_branch_exists
    by_node: dict[str, dict] = {}
    for entry in reg.get("entries") or []:
        node_id = entry.get("node_id")
        if node_id and node_id not in by_node:
            by_node[node_id] = entry
    claims: list[InFlightClaim] = []
    for node_id in active_ids:
        entry = by_node.get(node_id)
        branch = (entry or {}).get("branch")
        if not branch or not check(repo_root, branch):
            continue
        claims.append(
            InFlightClaim(
                node_id=node_id,
                codename=entry.get("codename") or "",
                branch=branch,
            )
        )
    return claims


def handle_no_ready(
    emitter,
    plan,
    finished: int,
    *,
    repo_root: Path,
    reg: dict,
    claims_fn=own_in_flight_claims,
) -> int:
    """Classify a cycle that found nothing ready, and emit the reason.

    In-flight is tested before blocked, and that order carries the fix. The two
    buckets are not mutually exclusive — in a healthy grind they almost always
    co-occur, because every leaf downstream of the in-flight one is blocked *on
    it*. "``blocked`` is non-empty" is therefore nearly always true at the
    moment the loop stops, and barely discriminates between the two situations;
    whether the operator holds the claim everything is waiting for does.

    The distinction earns its own exit code because the required responses are
    opposite. A dependency block needs a human to go and do something else. An
    open claim needs ``finish-this-task`` or ``abort-task-pickup`` and a re-run,
    which takes no judgement and can be driven unattended.
    """
    claims = claims_fn(repo_root, reg, plan.active)
    if claims:
        first = claims[0]
        branch_complete = node_complete_on_ref(repo_root, first.branch, first.node_id)
        emitter.emit(
            "in_flight",
            node_id=first.node_id,
            codename=first.codename,
            branch=first.branch,
            count=len(claims),
            others=[c.node_id for c in claims[1:]],
            branch_complete=branch_complete,
        )
        return EXIT_IN_FLIGHT
    if plan.blocked:
        b = plan.blocked[0]
        emitter.emit(
            "blocked",
            reason=b.reason,
            waiting_on=b.waiting_on,
            count=len(plan.blocked),
            node_id=b.node_id,
        )
        return EXIT_BLOCKED
    if finished > 0:
        emitter.emit("stopped", reason="no_work")
        return EXIT_OK
    emitter.emit("stopped", reason="no_actionable_leaves")
    return EXIT_NO_LEAVES


def checkout_branch(repo_root: Path, branch: str) -> tuple[int, str]:
    return git_code(["checkout", branch], repo_root)


def prepare_resume(
    repo_root: Path,
    claim: InFlightClaim,
    nodes: list[dict],
    *,
    on_complete: str,
    checkout=None,
) -> str | None:
    """Check out a claim's branch and restore its pickup artifacts.

    Returns an error string, or ``None`` when the branch is ready to implement
    against. The artifacts are rewritten **only when missing**: a resumed run
    usually still has the originals, and an operator who edited the prompt to
    steer the implementer would not expect a re-run to discard that.
    """
    code, out = (checkout or checkout_branch)(repo_root, claim.branch)
    if code != 0:
        return f"git checkout {claim.branch} failed: {out}"
    node = next((n for n in nodes if n.get("id") == claim.node_id), None)
    if node is None:
        return (
            f"{claim.node_id} is claimed on {claim.branch} but is not in the "
            "roadmap graph; run specy-road abort-task-pickup to release it."
        )
    _restore_artifacts(repo_root, node, nodes, on_complete=on_complete)
    return None


def _restore_artifacts(
    repo_root: Path, node: dict, nodes: list[dict], *, on_complete: str
) -> None:
    # Imported here rather than at module scope: the pickup helpers pull in the
    # brief renderer and the prompt writer, and nothing else here needs them.
    from specy_road.bundled_scripts.do_next_task_pickup_helpers import (
        write_brief,
        write_session_and_prompt,
    )

    work_dir = repo_root / "work"
    node_id = node["id"]
    brief_path = work_dir / f"brief-{node_id}.md"
    if not brief_path.exists():
        brief_path = write_brief(work_dir, node, nodes)
    if not (work_dir / f"prompt-{node_id}.md").exists():
        write_session_and_prompt(
            work_dir=work_dir,
            repo_root=repo_root,
            node=node,
            nodes=nodes,
            brief_path=brief_path,
            on_complete=on_complete,
        )
