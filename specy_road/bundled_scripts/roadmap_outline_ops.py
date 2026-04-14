"""Outline move/reorder: update parent_id + sibling_order, renumber display ids, persist chunks."""

from __future__ import annotations

from pathlib import Path

from roadmap_chunk_utils import load_json_chunk, roadmap_dir, write_json_chunk
from roadmap_crud_ops import run_validate_raise
from roadmap_gui_tree import indent_parent_id, outdent_parent_id
from roadmap_layout import sibling_sort_key
from roadmap_load import load_manifest_mapping, load_roadmap
from roadmap_node_keys import build_key_to_node
from roadmap_outline_renumber import can_indent_to_parent, renumber_display_ids_inplace
from sync_planning_artifacts import sync_planning_artifacts


def _chunk_includes(root: Path) -> list[str]:
    doc = load_manifest_mapping(root)
    inc = doc.get("includes") or []
    return [x for x in inc if isinstance(x, str) and x.strip()]


def persist_merged_nodes(root: Path, merged: list[dict]) -> None:
    """Write merged node list back to JSON chunks (match by ``node_key``, preserve chunk order)."""
    by_key = {n["node_key"]: n for n in merged}
    base = roadmap_dir(root)
    for rel in _chunk_includes(root):
        path = (base / rel).resolve()
        if not path.is_file() or path.suffix.lower() != ".json":
            continue
        chunk_nodes = load_json_chunk(path)
        out = []
        for old in chunk_nodes:
            k = old.get("node_key")
            if not isinstance(k, str) or k not in by_key:
                raise ValueError(f"chunk {rel}: unknown node_key {k!r}")
            out.append(by_key[k])
        write_json_chunk(path, out)


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
) -> None:
    """Set sibling_order for children of parent_id and renumber all display ids."""
    nodes = list(load_roadmap(root)["nodes"])
    by_id = {n["id"]: n for n in nodes}
    cur = _siblings(nodes, parent_id, by_id)
    if set(cur) != set(ordered_child_ids) or len(cur) != len(ordered_child_ids):
        raise ValueError("ordered_child_ids must match current children of parent_id")
    for i, nid in enumerate(ordered_child_ids):
        by_id[nid]["sibling_order"] = i
    old_to_new = renumber_display_ids_inplace(nodes)
    sync_planning_artifacts(root, nodes)
    persist_merged_nodes(root, nodes)
    sync_registry_node_ids(root, old_to_new)
    run_validate_raise(root)


def _validate_reparent_target(
    by_id: dict[str, dict],
    old_id: str,
    new_parent_id: str | None,
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
) -> None:
    """
    Reparent ``node_key`` under ``new_parent_id`` (None = root) at sibling index ``new_index``.
    Renumbers display ids for the whole roadmap. Subtree moves with the node.
    """
    nodes = list(load_roadmap(root)["nodes"])
    by_key = build_key_to_node(nodes)
    if node_key not in by_key:
        raise ValueError(f"unknown node_key {node_key!r}")
    by_id = {n["id"]: n for n in nodes}
    moved = by_key[node_key]
    old_id = moved["id"]
    _validate_reparent_target(by_id, old_id, new_parent_id)
    old_parent = moved.get("parent_id")
    _detach_reindex_old_parent(nodes, by_id, old_parent, old_id)
    _attach_at_index(nodes, by_id, moved, old_id, new_parent_id, new_index)
    old_to_new = renumber_display_ids_inplace(nodes)
    sync_planning_artifacts(root, nodes)
    persist_merged_nodes(root, nodes)
    sync_registry_node_ids(root, old_to_new)
    run_validate_raise(root)


def apply_indent(repo_root: Path, node_id: str) -> bool:
    """Nest under the sibling above (same parent). Returns False if no-op."""
    nodes = list(load_roadmap(repo_root)["nodes"])
    by_id = {n["id"]: n for n in nodes}
    new_parent = indent_parent_id(by_id, node_id)
    if new_parent is None:
        return False
    if not can_indent_to_parent(nodes, by_id, node_id, new_parent):
        return False
    nk = by_id[node_id]["node_key"]
    sibs = [
        n["id"]
        for n in nodes
        if (n.get("parent_id") or None) == new_parent and n["id"] != node_id
    ]
    sibs.sort(key=lambda x: sibling_sort_key(x, by_id))
    move_node_outline(repo_root, nk, new_parent, len(sibs))
    return True


def apply_outdent(repo_root: Path, node_id: str) -> bool:
    """Become sibling after former parent. Returns False if no-op."""
    nodes = list(load_roadmap(repo_root)["nodes"])
    by_id = {n["id"]: n for n in nodes}
    target = outdent_parent_id(by_id, node_id)
    if target is None:
        return False
    n = by_id[node_id]
    parent_of = n.get("parent_id")
    if not parent_of:
        return False
    new_parent_id = None if target == "" else target
    gp_sibs = ordered_sibling_ids(nodes, new_parent_id, by_id)
    pi = gp_sibs.index(parent_of)
    move_node_outline(repo_root, n["node_key"], new_parent_id, pi + 1)
    return True


def sync_registry_node_ids(root: Path, old_to_new: dict[str, str]) -> None:
    """Update roadmap/registry.yaml entry ``node_id`` when display ids change."""
    reg_path = root / "roadmap" / "registry.yaml"
    if not reg_path.is_file():
        return
    if not old_to_new:
        return
    # Minimal approach: replace exact node_id lines (quoted values avoided; YAML simple case)
    import yaml

    data = yaml.safe_load(reg_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return
    entries = data.get("entries")
    if not isinstance(entries, list):
        return
    changed = False
    for e in entries:
        if not isinstance(e, dict):
            continue
        nid = e.get("node_id")
        if isinstance(nid, str) and nid in old_to_new:
            e["node_id"] = old_to_new[nid]
            changed = True
    if changed:
        reg_path.write_text(
            yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )


