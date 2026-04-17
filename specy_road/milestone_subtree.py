"""Milestone subtree: structural leaves under a parent node (outline / parent_id tree)."""

from __future__ import annotations


def structural_leaf_ids(nodes: list[dict]) -> set[str]:
    """Nodes that are not parents of any other node (same as do-next structural leaves)."""
    parent_ids = {
        n.get("parent_id")
        for n in nodes
        if isinstance(n.get("parent_id"), str) and n.get("parent_id")
    }
    return {n["id"] for n in nodes if n.get("id") not in parent_ids}


def children_by_parent_id(nodes: list[dict]) -> dict[str | None, list[str]]:
    """Map parent_id (None for roots) to child node ids."""
    out: dict[str | None, list[str]] = {}
    for n in nodes:
        nid = n.get("id")
        if not isinstance(nid, str) or not nid:
            continue
        pid = n.get("parent_id")
        if pid in (None, ""):
            key: str | None = None
        else:
            key = str(pid)
        out.setdefault(key, []).append(nid)
    return out


def subtree_node_ids(root_id: str, nodes: list[dict]) -> set[str]:
    """
    All node ids in the subtree rooted at ``root_id``, including ``root_id``.

    Unknown ``root_id`` returns the empty set.
    """
    ids = {n.get("id") for n in nodes if isinstance(n.get("id"), str)}
    if root_id not in ids:
        return set()
    by_parent = children_by_parent_id(nodes)
    out: set[str] = set()
    stack = [root_id]
    while stack:
        cur = stack.pop()
        if cur in out:
            continue
        out.add(cur)
        for c in by_parent.get(cur, []):
            if c not in out:
                stack.append(c)
    return out


def leaf_ids_under_parent(parent_id: str, nodes: list[dict]) -> set[str]:
    """Structural leaf node ids that lie in ``parent_id``'s subtree (including under nested parents)."""
    scope = subtree_node_ids(parent_id, nodes)
    leaves = structural_leaf_ids(nodes)
    return leaves & scope


def filter_available_under_parent(
    available: list[dict],
    parent_id: str,
    nodes: list[dict],
) -> list[dict]:
    """Keep only nodes whose id is in the subtree of ``parent_id`` (order preserved)."""
    scope = subtree_node_ids(parent_id, nodes)
    return [n for n in available if n.get("id") in scope]
