"""Read/write ``milestone_execution`` on roadmap JSON chunks (requires bundled_scripts on path)."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from specy_road.milestone_subtree import leaf_ids_under_parent
from specy_road.runtime_paths import bundled_scripts_dir


def ensure_bundled_scripts_on_path() -> None:
    d = str(bundled_scripts_dir())
    if d not in sys.path:
        sys.path.insert(0, d)


def build_active_milestone_execution(
    *,
    rollup_branch: str,
    integration_branch: str,
    remote: str,
) -> dict[str, Any]:
    return {
        "state": "active",
        "rollup_branch": rollup_branch,
        "integration_branch": integration_branch,
        "remote": remote,
        "opened_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }


def write_milestone_execution(
    root: Path,
    parent_node_id: str,
    doc: dict[str, Any] | None,
) -> Path:
    """Set or remove ``milestone_execution`` on ``parent_node_id``; validate and save chunk."""
    ensure_bundled_scripts_on_path()
    from roadmap_chunk_utils import find_chunk_path, load_json_chunk, write_json_chunk
    from roadmap_crud_ops import node_index_in_chunk, run_validate_raise

    chunk = find_chunk_path(root, parent_node_id)
    if not chunk:
        raise ValueError(f"no chunk for node {parent_node_id!r}")
    nodes = load_json_chunk(chunk)
    idx = node_index_in_chunk(nodes, parent_node_id)
    if idx is None:
        raise ValueError(f"node {parent_node_id!r} not in chunk")
    node = nodes[idx]
    if not isinstance(node, dict):
        raise ValueError("corrupt node")
    if doc is None:
        node.pop("milestone_execution", None)
    else:
        node["milestone_execution"] = doc
    write_json_chunk(chunk, nodes)
    run_validate_raise(root)
    return chunk


def patch_milestone_execution_state(
    root: Path,
    parent_node_id: str,
    *,
    state: str,
    extra: dict[str, Any] | None = None,
) -> Path:
    """Load node, merge ``state`` (and optional keys) into ``milestone_execution``, save."""
    ensure_bundled_scripts_on_path()
    from roadmap_chunk_utils import find_chunk_path, load_json_chunk, write_json_chunk
    from roadmap_crud_ops import node_index_in_chunk, run_validate_raise

    chunk = find_chunk_path(root, parent_node_id)
    if not chunk:
        raise ValueError(f"no chunk for node {parent_node_id!r}")
    nodes = load_json_chunk(chunk)
    idx = node_index_in_chunk(nodes, parent_node_id)
    if idx is None:
        raise ValueError(f"node {parent_node_id!r} not in chunk")
    node = nodes[idx]
    if not isinstance(node, dict):
        raise ValueError("corrupt node")
    me = node.get("milestone_execution")
    if not isinstance(me, dict):
        raise ValueError(f"node {parent_node_id!r} has no milestone_execution to patch")
    prev_state = me.get("state")
    me = {**me, "state": state}
    if extra:
        me.update(extra)
    if state == "closed" and prev_state != "closed":
        me["closed_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    node["milestone_execution"] = me
    write_json_chunk(chunk, nodes)
    run_validate_raise(root)
    return chunk


def maybe_promote_milestone_to_pending_mr(
    root: Path,
    parent_node_id: str,
    nodes: list[dict],
) -> bool:
    """If every structural leaf under parent is Complete, set execution state to pending_mr."""
    ensure_bundled_scripts_on_path()

    leaves = leaf_ids_under_parent(parent_node_id, nodes)
    by_id = {n["id"]: n for n in nodes if isinstance(n.get("id"), str)}
    if not leaves:
        return False
    for lid in leaves:
        n = by_id.get(lid)
        st = (n or {}).get("status")
        if st != "Complete":
            return False
    parent = by_id.get(parent_node_id)
    if not parent:
        return False
    me = parent.get("milestone_execution")
    if not isinstance(me, dict) or me.get("state") != "active":
        return False
    patch_milestone_execution_state(root, parent_node_id, state="pending_mr")
    return True
