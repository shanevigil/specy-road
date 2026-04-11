"""Outline parent helpers for the PM GUI and roadmap outline ops (indent / outdent)."""

from __future__ import annotations

from roadmap_layout import sibling_sort_key
from roadmap_outline_renumber import can_indent_to_parent


def row_index(tree_rows: list[tuple[dict, int]], nid: str) -> int | None:
    for i, (n, _) in enumerate(tree_rows):
        if n["id"] == nid:
            return i
    return None


def is_ancestor(by_id: dict, ancestor_id: str, nid: str) -> bool:
    cur: str | None = by_id[nid].get("parent_id")
    while cur:
        if cur == ancestor_id:
            return True
        cur = by_id[cur].get("parent_id")
    return False


def outdent_parent_id(by_id: dict, nid: str) -> str | None:
    pid: str | None = by_id[nid].get("parent_id")
    if not pid:
        return None
    grand = by_id[pid].get("parent_id")
    return grand if grand else ""


def indent_parent_id(by_id: dict, nid: str) -> str | None:
    """
    Tab indent: nest under the sibling directly above (same parent).

    Returns that sibling's id as the new parent, or None if there is no
    previous sibling (e.g. first child under a parent) or node is missing.
    """
    n = by_id.get(nid)
    if not n:
        return None
    parent = n.get("parent_id") or None
    siblings = [
        x["id"]
        for x in by_id.values()
        if (x.get("parent_id") or None) == parent
    ]
    siblings.sort(key=lambda sid: sibling_sort_key(sid, by_id))
    try:
        ix = siblings.index(nid)
    except ValueError:
        return None
    if ix < 1:
        return None
    return siblings[ix - 1]


def can_indent_outline(nodes: list[dict], by_id: dict, nid: str) -> bool:
    """True if Tab-indent would reparent (sibling exists and depth allows)."""
    newp = indent_parent_id(by_id, nid)
    if newp is None:
        return False
    return can_indent_to_parent(nodes, by_id, nid, newp)


def can_outdent_outline(by_id: dict, nid: str) -> bool:
    """True if outdent has a valid grandparent/root target."""
    return outdent_parent_id(by_id, nid) is not None
