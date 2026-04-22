"""Node CRUD and outline mutation API routes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from roadmap_chunk_utils import find_chunk_path, roadmap_dir
from roadmap_crud_ops import (
    append_node_to_chunk,
    delete_roadmap_node_hard,
    edit_node_set_pairs,
    merged_ids,
    run_validate_raise,
)
from roadmap_load import load_roadmap
from roadmap_node_keys import new_node_key
from roadmap_layout import sibling_sort_key
from roadmap_outline_ops import (
    apply_indent,
    apply_outdent,
    move_node_outline,
    persist_merged_nodes,
    reorder_siblings,
    sync_registry_node_ids,
)
from roadmap_outline_renumber import renumber_display_ids_inplace
from sync_planning_artifacts import sync_planning_artifacts
from planning_sheet_bootstrap import ensure_planning_sheet_for_new_node

from specy_road.gui_app_helpers import get_repo_root, next_child_id
from specy_road.gui_app_models import AddNodeBody, MoveOutlineBody, PatchBody, ReorderBody
from specy_road.milestone_lock import assert_pm_nodes_not_milestone_locked
from specy_road.pm_gui_concurrency import require_pm_gui_write_header


def _pm_milestone_lock_guard(root: Path, *node_ids: str | None) -> None:
    ids = [x for x in node_ids if isinstance(x, str) and x.strip()]
    if not ids:
        return
    nodes = load_roadmap(root)["nodes"]
    try:
        assert_pm_nodes_not_milestone_locked(nodes, *ids)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e


def _node_id_for_key(nodes: list[dict[str, Any]], node_key: str) -> str | None:
    for n in nodes:
        if n.get("node_key") == node_key:
            sid = n.get("id")
            return sid if isinstance(sid, str) else None
    return None


def _canonical_ids_after_add(
    root: Path, provisional_new_id: str, inserted_node_key: str
) -> str:
    """Renumber display ids after insert (same pipeline as outline reorder)."""
    nodes3 = list(load_roadmap(root)["nodes"])
    old_to_new = renumber_display_ids_inplace(nodes3)
    sync_planning_artifacts(root, nodes3)
    persist_merged_nodes(root, nodes3)
    sync_registry_node_ids(root, old_to_new)
    run_validate_raise(root)
    return next(
        (n["id"] for n in nodes3 if n.get("node_key") == inserted_node_key),
        old_to_new.get(provisional_new_id, provisional_new_id),
    )


def _api_add_node_impl(root: Path, body: AddNodeBody) -> dict[str, Any]:
    nodes = load_roadmap(root)["nodes"]
    by_id = {n["id"]: n for n in nodes}
    ref = body.reference_node_id
    _pm_milestone_lock_guard(root, ref)
    if ref not in by_id:
        raise HTTPException(status_code=404, detail="reference node not found")
    ref_node = by_id[ref]
    parent_id: str | None = ref_node.get("parent_id")
    if body.type == "gate" and parent_id in (None, ""):
        raise HTTPException(
            status_code=400,
            detail=(
                "gate requires a parent vision or phase; select a row under "
                "a phase (not a top-level row)"
            ),
        )
    chunk_path = find_chunk_path(root, ref)
    if not chunk_path:
        raise HTTPException(status_code=500, detail="chunk for reference not found")
    chunk_arg = str(chunk_path.relative_to(roadmap_dir(root)))

    siblings = [n["id"] for n in nodes if n.get("parent_id") == parent_id]
    siblings.sort(key=lambda nid: sibling_sort_key(nid, by_id))
    if ref not in siblings:
        raise HTTPException(status_code=400, detail="reference not in sibling list")

    ix = siblings.index(ref)
    insert_at = ix if body.position == "above" else ix + 1

    new_id = next_child_id(nodes, parent_id)
    if new_id in merged_ids(root):
        raise HTTPException(status_code=409, detail="generated id already exists")

    new_node: dict[str, Any] = {
        "id": new_id,
        "node_key": new_node_key(),
        "parent_id": parent_id,
        "type": body.type,
        "title": body.title,
        "status": "Not Started",
        "dependencies": [],
        "touch_zones": [],
    }

    ensure_planning_sheet_for_new_node(root, new_node)
    inserted_key = new_node["node_key"]

    try:
        append_node_to_chunk(root, chunk_arg, new_node)
        run_validate_raise(root)
    except (SystemExit, OSError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    nodes2 = load_roadmap(root)["nodes"]
    by_id2 = {n["id"]: n for n in nodes2}
    sib = [n["id"] for n in nodes2 if n.get("parent_id") == parent_id]
    sib.sort(key=lambda nid: sibling_sort_key(nid, by_id2))
    if new_id not in sib:
        raise HTTPException(status_code=500, detail="new node missing after add")
    sib.remove(new_id)
    sib.insert(insert_at, new_id)
    try:
        for i, nid in enumerate(sib):
            edit_node_set_pairs(root, nid, [("sibling_order", str(i))])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    try:
        final_id = _canonical_ids_after_add(root, new_id, inserted_key)
    except (SystemExit, OSError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": "true", "id": final_id}


def register_node_mutations(api: APIRouter) -> None:
    @api.patch("/nodes/{node_id}")
    def api_patch_node(
        node_id: str,
        body: PatchBody,
        _pm: None = Depends(require_pm_gui_write_header),
    ) -> dict[str, str]:
        root = get_repo_root()
        _pm_milestone_lock_guard(root, node_id)
        pairs = [(p.key, p.value) for p in body.pairs]
        try:
            edit_node_set_pairs(root, node_id, pairs)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return {"ok": "true", "node_id": node_id}

    @api.delete("/nodes/{node_id}")
    def api_delete_node(
        node_id: str,
        _pm: None = Depends(require_pm_gui_write_header),
    ) -> dict[str, str]:
        root = get_repo_root()
        _pm_milestone_lock_guard(root, node_id)
        try:
            delete_roadmap_node_hard(root, node_id)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return {"ok": "true", "node_id": node_id}

    @api.post("/outline/reorder")
    def api_reorder(
        body: ReorderBody,
        _pm: None = Depends(require_pm_gui_write_header),
    ) -> dict[str, str]:
        root = get_repo_root()
        _pm_milestone_lock_guard(root, *body.ordered_child_ids)
        pid: str | None = body.parent_id
        try:
            reorder_siblings(root, pid, body.ordered_child_ids)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return {"ok": "true"}

    @api.post("/outline/move")
    def api_outline_move(
        body: MoveOutlineBody,
        _pm: None = Depends(require_pm_gui_write_header),
    ) -> dict[str, str]:
        root = get_repo_root()
        nodes0 = load_roadmap(root)["nodes"]
        moved_id = _node_id_for_key(nodes0, body.node_key)
        if not moved_id:
            # Pre-existing contract (still asserted by tests) is 400 for an
            # unknown node_key — ``move_node_outline`` previously raised
            # ``ValueError("unknown node_key …")`` and the route mapped it to
            # 400. Keep that semantic now that we resolve the key early so the
            # milestone lock guard can check the moved id.
            raise HTTPException(
                status_code=400, detail=f"unknown node_key {body.node_key!r}"
            )
        _pm_milestone_lock_guard(root, moved_id, body.new_parent_id)
        try:
            move_node_outline(
                root,
                body.node_key,
                body.new_parent_id,
                body.new_index,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return {"ok": "true"}

    @api.post("/nodes/{node_id}/indent")
    def api_indent(
        node_id: str,
        _pm: None = Depends(require_pm_gui_write_header),
    ) -> dict[str, Any]:
        root = get_repo_root()
        _pm_milestone_lock_guard(root, node_id)
        try:
            changed = apply_indent(root, node_id)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return {"ok": True, "changed": changed}

    @api.post("/nodes/{node_id}/outdent")
    def api_outdent(
        node_id: str,
        _pm: None = Depends(require_pm_gui_write_header),
    ) -> dict[str, Any]:
        root = get_repo_root()
        _pm_milestone_lock_guard(root, node_id)
        try:
            changed = apply_outdent(root, node_id)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return {"ok": True, "changed": changed}


def register_add_node(api: APIRouter) -> None:
    @api.post("/nodes/add")
    def api_add_node(
        body: AddNodeBody,
        _pm: None = Depends(require_pm_gui_write_header),
    ) -> dict[str, Any]:
        return _api_add_node_impl(get_repo_root(), body)
