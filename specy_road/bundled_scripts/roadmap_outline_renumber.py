"""Display-id renumbering (node_key stable).

Two forms: :func:`renumber_display_ids_inplace` rewrites every id from the
tree shape (the PM GUI's outline drag, ``move-node --renumber-outline``), and
:func:`assign_subtree_ids_inplace` renumbers only a moved subtree
(``move-node``'s default), so no other node's id changes.
"""

from __future__ import annotations

from collections import defaultdict

from specy_road.bundled_scripts.roadmap_layout import sibling_sort_key
from specy_road.node_kinds import allows_children, parent_type_allowed

# Maximum dot-separated segments in a display id (M0.1.2 = 3 segments).
MAX_OUTLINE_DEPTH = 8


def outline_depth_from_id(nid: str) -> int:
    """Number of segments (M0 -> 1, M0.1 -> 2)."""
    if not nid or not nid.startswith("M"):
        return 0
    rest = nid[1:]
    if not rest:
        return 1
    return 1 + rest.count(".")


def max_edge_depth_below(nodes: list[dict], root_id: str) -> int:
    """Longest downward chain of parent/child edges under ``root_id`` (0 if leaf)."""
    best = 0
    for n in nodes:
        if n.get("parent_id") != root_id:
            continue
        best = max(best, 1 + max_edge_depth_below(nodes, n["id"]))
    return best


def can_indent_to_parent(
    nodes: list[dict],
    by_id: dict[str, dict],
    node_id: str,
    new_parent_id: str,
) -> bool:
    """Reject indent if any node in the moved subtree would exceed MAX_OUTLINE_DEPTH."""
    n = by_id.get(node_id)
    p = by_id.get(new_parent_id)
    if not n or not p:
        return False
    if not allows_children(p):
        return False
    if not parent_type_allowed(n.get("type"), p.get("type")):
        return False
    parent_seg = outline_depth_from_id(new_parent_id)
    # After reparent: node sits at parent_seg+1; deepest descendant adds edges below node.
    down = max_edge_depth_below(nodes, node_id)
    deepest_seg = parent_seg + 1 + down
    return deepest_seg <= MAX_OUTLINE_DEPTH


def _children_by_parent(
    nodes: list[dict],
    by_id: dict[str, dict],
) -> dict[str | None, list[dict]]:
    ch: dict[str | None, list[dict]] = defaultdict(list)
    for n in nodes:
        pid = n.get("parent_id")
        if pid is not None and pid not in by_id:
            pid = None
        ch[pid].append(n)
    for lst in ch.values():
        lst.sort(key=lambda x: (sibling_sort_key(x["id"], by_id), x.get("node_key", "")))
    return ch


def renumber_display_ids_inplace(nodes: list[dict]) -> dict[str, str]:
    """
    Reassign every node's ``id`` and ``parent_id`` from tree structure (``parent_id``
    links and sibling order). ``node_key`` and ``dependencies`` (node_keys) unchanged.
    Roots keep the project's numbering base: ``M0, M1, …`` when a root is ``M0``
    today, else ``M1, M2, …`` (the ``init project`` scaffold starts at ``M1``).

    Returns map old_id -> new_id for diagnostics/registry updates.
    """
    by_old_id = {n["id"]: n for n in nodes}
    ch_map = _children_by_parent(nodes, by_old_id)
    key_to_new_id: dict[str, str] = {}

    def visit(new_parent_id: str | None, children: list[dict]) -> None:
        for i, n in enumerate(children):
            nk = n.get("node_key")
            if not isinstance(nk, str) or not nk:
                raise ValueError(f"node missing node_key: {n!r}")
            old_id = n["id"]
            if new_parent_id is None:
                new_id = f"M{base + i}"
            else:
                new_id = f"{new_parent_id}.{i + 1}"
            key_to_new_id[nk] = new_id
            subs = ch_map.get(old_id, [])
            visit(new_id, subs)

    roots = ch_map.get(None, [])
    base = 0 if any(n["id"] == "M0" for n in roots) else 1
    visit(None, roots)

    old_to_new = {n["id"]: key_to_new_id[n["node_key"]] for n in nodes}

    for n in nodes:
        nk = n["node_key"]
        n["id"] = key_to_new_id[nk]
        pid = n.get("parent_id")
        if pid is None:
            n["parent_id"] = None
        else:
            p = by_old_id.get(pid)
            if not p:
                n["parent_id"] = None
            else:
                pk = p["node_key"]
                n["parent_id"] = key_to_new_id[pk]
    return old_to_new


def _numeric_last_segment(nid: str, prefix: str) -> int | None:
    """``k`` when ``nid`` is ``<prefix><k>`` with an integer ``k``, else None."""
    if not nid.startswith(prefix):
        return None
    rest = nid[len(prefix):]
    return int(rest) if rest.isdigit() else None


def next_free_child_id(
    nodes: list[dict], parent_id: str | None, *, exclude_key: str | None = None
) -> str:
    """One past the highest numbered child of ``parent_id`` (``None`` = root).

    Gaps are left alone, so no existing sibling's id changes. ``exclude_key``
    leaves the node being moved out of the count, so moving the last child of
    a parent back under it keeps its number.
    """
    prefix = "M" if parent_id is None else f"{parent_id}."
    taken = [
        _numeric_last_segment(n["id"], prefix)
        for n in nodes
        if (n.get("parent_id") or None) == parent_id
        and n.get("node_key") != exclude_key
    ]
    highest = max((k for k in taken if k is not None), default=0)
    return f"{prefix}{highest + 1}"


def assign_subtree_ids_inplace(
    nodes: list[dict], moved_key: str, new_id: str
) -> dict[str, str]:
    """Give the node ``moved_key`` the id ``new_id`` and renumber its subtree only.

    Each descendant keeps its own last id segment under its parent's new id
    (``M1.2.3`` moved to ``M4.7`` becomes ``M4.7.3``), so gaps inside the
    subtree survive. Every other node keeps its ``id`` and ``parent_id``; the
    moved node's ``parent_id`` is whatever the caller already set. Returns
    ``old_id -> new_id`` for the subtree only.
    """
    moved = next(n for n in nodes if n.get("node_key") == moved_key)
    children: dict[str, list[dict]] = defaultdict(list)
    for n in nodes:
        if n is not moved and isinstance(n.get("parent_id"), str):
            children[n["parent_id"]].append(n)

    # (node, new id, new parent id); collected before anything is rewritten.
    renames: list[tuple[dict, str, str | None]] = []

    def visit(node: dict, nid: str, parent: str | None) -> None:
        renames.append((node, nid, parent))
        for child in children.get(node["id"], []):
            visit(child, f"{nid}.{child['id'].rsplit('.', 1)[-1]}", nid)

    visit(moved, new_id, moved.get("parent_id"))
    old_to_new = {node["id"]: nid for node, nid, _parent in renames}
    for node, nid, parent in renames:
        node["id"] = nid
        node["parent_id"] = parent
    return old_to_new
