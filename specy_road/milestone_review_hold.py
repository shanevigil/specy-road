"""Milestone full-review hold: demote rollups and surface hold reasons.

Extracted from :mod:`specy_road.finish_ancestor_rollup` so the graph loader does
not import the rollup or review stack. :func:`demote_pending_milestone_rollups`
is still applied on every public graph load via :mod:`specy_road.roadmap_load`.
"""

from __future__ import annotations

from pathlib import Path

from specy_road.orchestration_config import effective_config
from specy_road.review_policy_ref import policy_source, review_required
from specy_road.review_target import ReviewTargetError, is_milestone, resolve_target
from specy_road.roadmap_graph import compute_rollup_status

UNRESOLVABLE_HOLD = "its full review cannot be evaluated"


def milestone_review_hold(repo_root: Path, nodes: list[dict], node_id: str) -> str | None:
    """Why ``node_id`` keeps its status while its full review is pending, else ``None``.

    Only a milestone under the review gate is held, and only while the policy
    is on. The gate is evaluated at the milestone's review target (the
    integration tip), and only once every leaf is Complete there: an approval
    recorded before the last leaf landed never releases the hold. A target
    that cannot be resolved holds too, since the review cannot have happened.
    A milestone whose authored status is already Complete has been closed;
    later integration commits (including the closure commit) do not reopen it.
    """
    if not is_milestone(nodes, node_id) or not review_required(repo_root):
        return None
    ref, _err = policy_source(repo_root)
    config, _err = effective_config(repo_root, ref)
    if not config["policy"].get("milestone_full_review", True):
        return None
    node = next(n for n in nodes if n.get("id") == node_id)
    if node.get("status") == "Complete":
        return None
    try:
        target = resolve_target(repo_root, node_id, nodes=nodes)
    except ReviewTargetError as e:
        return f"{UNRESOLVABLE_HOLD} ({e})"
    if target.unfinished_leaves:   # a review of the tip before the last leaf landed covers less than the milestone
        return f"its leaves {', '.join(target.unfinished_leaves)} have not landed on {target.ref}"
    from specy_road.review_gate import evaluate_gate   # the whole gate, only for a held milestone

    gate = evaluate_gate(repo_root, node, target.commit)
    if gate.passed:
        return None
    return f"its full review is not approved at {target.ref} ({gate.summary()})"


def demote_pending_milestone_rollups(repo_root: Path, nodes: list[dict]) -> None:
    """Keep a held milestone's computed rollup non-Complete on the public loader.

    ``compute_rollup_status`` is still leaf-based (dependency satisfaction).
    A recorded closure (authored ``status`` Complete) is left Complete: the
    status commit and later integration work must not reopen it. When the
    target cannot be resolved the leaf rollup is left unchanged: a graph
    without git must not look held.
    """
    for n in nodes:
        nid = n.get("id")
        if n.get("rollup_status") != "Complete" or not isinstance(nid, str):
            continue
        why = milestone_review_hold(repo_root, nodes, nid)
        if why and not why.startswith(UNRESOLVABLE_HOLD):
            n["rollup_status"] = "In Progress"


def _review_commands(node_id: str) -> str:
    return (
        f"specy-road review-packet {node_id}; each reviewer: "
        f"specy-road review record {node_id} --model <id> --verdict approve|block --file <notes.md>; "
        f"then specy-road mark-implementation-reviewed {node_id}"
    )


def milestone_review_next_steps(node_id: str) -> str:
    return f"  Next, once this branch has landed: {_review_commands(node_id)} (policy.milestone_full_review)"


def held_milestones(repo_root: Path, nodes: list[dict]) -> dict[str, str]:
    """``{milestone id: hold reason}`` for each milestone whose leaves are all Complete but which is held."""
    leaf = compute_rollup_status(nodes)
    out: dict[str, str] = {}
    for n in nodes:
        nid = n.get("id")
        if isinstance(nid, str) and leaf.get(nid) == "Complete" and n.get("status") != "Complete":
            why = milestone_review_hold(repo_root, nodes, nid)
            if why:
                out[nid] = why
    return out


def milestone_review_hold_notice(node_id: str, why: str) -> str:
    """The notice validate and why-blocked print for a held milestone: the reason and the three ways out.

    A hold whose review target cannot be resolved does not demote the rollup
    (see :func:`demote_pending_milestone_rollups`), so it gets one line only.
    """
    if why.startswith(UNRESOLVABLE_HOLD):
        return (
            f"milestone review: notice — {node_id}: {why} (policy.milestone_full_review); "
            "its rollup follows its leaves"
        )
    return "\n".join([
        f"milestone review: notice — {node_id} is held at In Progress: every leaf is Complete but {why} "
        "(policy.milestone_full_review). Ways out:",
        f"  1. Review it: {_review_commands(node_id)}",
        f"  2. Record it Complete: specy-road edit-node {node_id} --set status=Complete",
        "  3. Turn the hold off: set policy.milestone_full_review: false in roadmap/orchestration.yaml",
    ])
