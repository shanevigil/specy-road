"""Outline move/reorder: update parent_id + sibling_order, renumber display ids (subtree-only by default), persist chunks."""

from __future__ import annotations

from pathlib import Path

from specy_road.bundled_scripts.roadmap_gui_tree import indent_parent_id, outdent_parent_id
from specy_road.bundled_scripts.roadmap_layout import sibling_sort_key
from specy_road.bundled_scripts.roadmap_load import load_roadmap
from specy_road.bundled_scripts.roadmap_outline_renumber import can_indent_to_parent, renumber_display_ids_inplace
from specy_road.node_kinds import allows_children, is_gate, parent_type_allowed


def ordered_sibling_ids(
    nodes: list[dict],
    parent_id: str | None,
    by_id: dict[str, dict],
) -> list[str]:
    s = [n["id"] for n in nodes if (n.get("parent_id") or None) == parent_id]
    s.sort(key=lambda nid: sibling_sort_key(nid, by_id))
    return s


def _siblings(nodes: list[dict], parent_id: str | None, by_id: dict[str, dict]) -> list[str]:
    return ordered_sibling_ids(nodes, parent_id, by_id)


def reorder_siblings(
    root: Path,
    parent_id: str | None,
    ordered_child_ids: list[str],
    *,
    renumber_outline: bool = False,
) -> None:
    """Set ``sibling_order`` for the children of ``parent_id``; no id changes.

    Outline order is ``sibling_order``-driven (``sibling_sort_key``), so a
    reorder needs no renumber. ``renumber_outline=True`` also renumbers every
    display id from the new shape. Either way the write is staged through one
    ``AtomicWritePlan`` and validated before anything reaches disk.
    """
    from specy_road.bundled_scripts.roadmap_move_node import stage_id_rewrite

    nodes = list(load_roadmap(root)["nodes"])
    by_id = {n["id"]: n for n in nodes}
    cur = _siblings(nodes, parent_id, by_id)
    if set(cur) != set(ordered_child_ids) or len(cur) != len(ordered_child_ids):
        raise ValueError("ordered_child_ids must match current children of parent_id")
    for i, nid in enumerate(ordered_child_ids):
        by_id[nid]["sibling_order"] = i
    old_to_new = renumber_display_ids_inplace(nodes) if renumber_outline else {}
    stage_id_rewrite(
        root,
        nodes,
        nodes if renumber_outline else [],
        old_to_new,
        claims_in_map_only=False,
    )


def _validate_reparent_target(
    by_id: dict[str, dict],
    old_id: str,
    new_parent_id: str | None,
    *,
    moved_type: str | None = None,
) -> None:
    if new_parent_id is not None and new_parent_id not in by_id:
        raise ValueError(f"unknown new_parent_id {new_parent_id!r}")
    if new_parent_id == old_id:
        raise ValueError("cannot move node under itself")
    cur: str | None = new_parent_id
    while cur:
        if cur == old_id:
            raise ValueError("cannot move node under its descendant")
        cur = by_id.get(cur, {}).get("parent_id")
    if new_parent_id is not None:
        parent = by_id.get(new_parent_id)
        if parent and not allows_children(parent):
            raise ValueError("cannot move node under a gate")
    if is_gate(moved_type):
        if new_parent_id is None:
            raise ValueError("gate must have a vision, phase, or milestone parent")
        np = by_id.get(new_parent_id)
        if not np or not parent_type_allowed(moved_type, np.get("type")):
            raise ValueError(
                "gate must be a direct child of vision, phase, or milestone"
            )


def _detach_reindex_old_parent(
    nodes: list[dict],
    by_id: dict[str, dict],
    old_parent: str | None,
    old_id: str,
) -> None:
    sib = _siblings(nodes, old_parent, by_id)
    if old_id not in sib:
        raise ValueError("corrupt tree: moved node not in old parent's children")
    sib = [x for x in sib if x != old_id]
    for i, nid in enumerate(sib):
        by_id[nid]["sibling_order"] = i


def _attach_at_index(
    nodes: list[dict],
    by_id: dict[str, dict],
    moved: dict,
    old_id: str,
    new_parent_id: str | None,
    new_index: int,
) -> None:
    moved["parent_id"] = new_parent_id
    by_id.clear()
    by_id.update({n["id"]: n for n in nodes})
    snew = [
        n["id"]
        for n in nodes
        if (n.get("parent_id") or None) == new_parent_id and n["id"] != old_id
    ]
    snew.sort(key=lambda nid: sibling_sort_key(nid, by_id))
    if new_index < 0 or new_index > len(snew):
        raise ValueError("new_index out of range")
    snew.insert(new_index, old_id)
    for i, nid in enumerate(snew):
        by_id[nid]["sibling_order"] = i


def move_node_outline(
    root: Path,
    node_key: str,
    new_parent_id: str | None,
    new_index: int,
    *,
    new_id: str | None = None,
    fill_gaps: bool = False,
    renumber_outline: bool = False,
    rewrite_refs: bool = False,
) -> dict[str, str]:
    """
    Reparent ``node_key`` under ``new_parent_id`` (None = root) at sibling index ``new_index``.
    Subtree moves with the node. Renumbers only the moved subtree, like the
    ``move-node`` CLI (``new_id`` / ``fill_gaps`` choose the moved node's id);
    ``renumber_outline=True`` renumbers display ids for the whole roadmap.

    Atomic: the chunk rewrites, planning-sheet renames and registry update are
    staged together and validated before any of them reaches disk. This used to
    persist all three and validate afterwards, so a rejected move left the
    roadmap unloadable — the same defect ``edit-node`` was fixed for in
    ``v0.1.4``. See ``bundled_scripts/roadmap_move_node.py``. Returns the
    ``old -> new`` id map. ``rewrite_refs`` also rewrites the map's ids in
    every node's planning sheet, title and acceptance (``rename-refs``).
    """
    from specy_road.bundled_scripts.roadmap_move_node import move_node

    return move_node(
        root,
        node_key,
        new_parent_id,
        new_index,
        renumber_outline=renumber_outline,
        new_id=new_id,
        fill_gaps=fill_gaps,
        rewrite_refs=rewrite_refs,
    )


def print_id_map(old_to_new: dict[str, str]) -> bool:
    """Print the ids that changed; return whether any did."""
    renamed = {o: n for o, n in old_to_new.items() if o != n}
    if not renamed:
        return False
    print("\nDisplay ids changed (an id is a position, not an identity):")
    for old, new in sorted(renamed.items()):
        print(f"  {old} -> {new}")
    return True


def _load_with_node(repo_root: Path, node_id: str) -> tuple[list[dict], dict[str, dict]]:
    """Load the graph for indent/outdent; an unknown ``node_id`` is a ``ValueError``."""
    nodes = list(load_roadmap(repo_root)["nodes"])
    by_id = {n["id"]: n for n in nodes}
    if node_id not in by_id:
        raise ValueError(f"unknown node id {node_id!r}")
    return nodes, by_id


def apply_indent(
    repo_root: Path,
    node_id: str,
    *,
    renumber_outline: bool = False,
    rewrite_refs: bool = False,
) -> dict[str, str] | None:
    """Nest under the sibling above (same parent). Returns the id map, None if no-op."""
    nodes, by_id = _load_with_node(repo_root, node_id)
    new_parent = indent_parent_id(by_id, node_id)
    if new_parent is None:
        return None
    if not can_indent_to_parent(nodes, by_id, node_id, new_parent):
        return None
    nk = by_id[node_id]["node_key"]
    sibs = [
        n["id"]
        for n in nodes
        if (n.get("parent_id") or None) == new_parent and n["id"] != node_id
    ]
    sibs.sort(key=lambda x: sibling_sort_key(x, by_id))
    return move_node_outline(
        repo_root,
        nk,
        new_parent,
        len(sibs),
        renumber_outline=renumber_outline,
        rewrite_refs=rewrite_refs,
    )


def apply_outdent(
    repo_root: Path,
    node_id: str,
    *,
    renumber_outline: bool = False,
    rewrite_refs: bool = False,
) -> dict[str, str] | None:
    """Become sibling after former parent. Returns the id map, None if no-op."""
    nodes, by_id = _load_with_node(repo_root, node_id)
    target = outdent_parent_id(by_id, node_id)
    if target is None:
        return None
    n = by_id[node_id]
    parent_of = n.get("parent_id")
    if not parent_of:
        return None
    new_parent_id = None if target == "" else target
    gp_sibs = ordered_sibling_ids(nodes, new_parent_id, by_id)
    pi = gp_sibs.index(parent_of)
    return move_node_outline(
        repo_root,
        n["node_key"],
        new_parent_id,
        pi + 1,
        renumber_outline=renumber_outline,
        rewrite_refs=rewrite_refs,
    )
