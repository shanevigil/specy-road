"""Outline parent helpers for scripts/roadmap_gui.py (indent / outdent)."""

from __future__ import annotations


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


def indent_parent_id(
    tree_rows: list[tuple[dict, int]],
    by_id: dict,
    nid: str,
) -> str | None:
    """New parent = row directly above (classic outline Tab). None if invalid."""
    idx = row_index(tree_rows, nid)
    if idx is None or idx < 1:
        return None
    prev_id = tree_rows[idx - 1][0]["id"]
    if prev_id == nid:
        return None
    if is_ancestor(by_id, nid, prev_id):
        return None
    return prev_id
