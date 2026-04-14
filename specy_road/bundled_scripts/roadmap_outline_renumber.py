"""Full-tree id renumbering from parent_id + sibling_order (display ids; node_key stable)."""

from __future__ import annotations

from collections import defaultdict

from roadmap_layout import sibling_sort_key

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

    Returns map old_id -> new_id for diagnostics/registry updates.
    """
    by_old_id = {n["id"]: n for n in nodes}
    ch_map = _children_by_parent(nodes, by_old_id)
    key_to_new_id: dict[str, str] = {}

    def visit(_: str | None, new_parent_id: str | None, children: list[dict]) -> None:
        for i, n in enumerate(children):
            nk = n.get("node_key")
            if not isinstance(nk, str) or not nk:
                raise ValueError(f"node missing node_key: {n!r}")
            old_id = n["id"]
            if new_parent_id is None:
                new_id = f"M{i}"
            else:
                new_id = f"{new_parent_id}.{i + 1}"
            key_to_new_id[nk] = new_id
            subs = ch_map.get(old_id, [])
            visit(old_id, new_id, subs)

    roots = ch_map.get(None, [])
    visit(None, None, roots)

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
