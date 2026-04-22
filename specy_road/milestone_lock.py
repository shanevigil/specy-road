"""PM subtree lock when ``milestone_execution`` is active or pending MR."""

from __future__ import annotations

from specy_road.milestone_subtree import subtree_node_ids

_LOCK_STATES = frozenset({"active", "pending_mr"})


def milestone_lock_parent_ids(nodes: list[dict]) -> list[str]:
    """Parent node ids that currently lock their subtree for PM edits."""
    out: list[str] = []
    for n in nodes:
        if not isinstance(n, dict):
            continue
        nid = n.get("id")
        me = n.get("milestone_execution")
        if not isinstance(nid, str) or not isinstance(me, dict):
            continue
        if me.get("state") in _LOCK_STATES:
            out.append(nid)
    return out


def locked_node_ids(nodes: list[dict]) -> frozenset[str]:
    """Union of subtree node ids (including the parent) under any locking milestone."""
    acc: set[str] = set()
    for pid in milestone_lock_parent_ids(nodes):
        acc |= subtree_node_ids(pid, nodes)
    return frozenset(acc)


def assert_pm_nodes_not_milestone_locked(nodes: list[dict], *node_ids: str) -> None:
    """Raise ValueError with a clear message if any id lies under a locked milestone."""
    locked = locked_node_ids(nodes)
    for nid in node_ids:
        if nid in locked:
            parents = milestone_lock_parent_ids(nodes)
            blocking = [p for p in parents if nid in subtree_node_ids(p, nodes)]
            hint = blocking[0] if blocking else "?"
            raise ValueError(
                f"roadmap node {nid!r} is inside milestone subtree {hint!r} with "
                f"active milestone execution (finish rollout / MR flow, or run "
                f"`specy-road reconcile-milestone-status` after delivery). "
                f"PM edits are blocked until the milestone is closed on the integration branch."
            )
