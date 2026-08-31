"""Node removal for the roadmap CRUD CLI (``archive-node --hard-remove``).

Split out of :mod:`roadmap_crud_ops` to stay inside the repo's per-file line
cap; the ``roadmap_crud_*`` modules follow the same pattern.

A node and its planning sheet go in one transaction. Unlinking the sheet before
validating the resulting graph would leave a repo that cannot validate whenever
the removal is refused (for example because another node still depends on it).

Not to be confused with ``specy-road archive`` (:mod:`specy_road.archive_ops`),
which moves completed work out of the live graph **reversibly**. The name
collision is historical.
"""

from __future__ import annotations

import sys
from pathlib import Path

from planning_artifacts import normalize_planning_dir, resolve_planning_path
from roadmap_chunk_atomic import AtomicWritePlan
from roadmap_chunk_utils import find_chunk_path, load_json_chunk
from roadmap_load import load_roadmap


def can_hard_remove(root: Path, node_id: str) -> tuple[bool, str]:
    """Whether ``node_id`` has no children and nothing depends on it."""
    nodes = load_roadmap(root)["nodes"]
    target_key: str | None = None
    for n in nodes:
        if n.get("id") == node_id:
            target_key = n.get("node_key")
            break
    for n in nodes:
        if n.get("parent_id") == node_id:
            return False, f"child node {n['id']} has parent_id {node_id!r}"
        if target_key and target_key in (n.get("dependencies") or []):
            return False, f"node {n['id']} depends on node_key of {node_id!r}"
    return True, ""


def planning_sheet_delete_plan(root: Path, planning_dir: object) -> Path | None:
    """Resolve ``planning_dir`` to the sheet to unlink, or ``None`` when there is none."""
    if not isinstance(planning_dir, str) or not planning_dir.strip():
        return None
    try:
        norm = normalize_planning_dir(planning_dir.strip())
    except ValueError:
        return None
    path = resolve_planning_path(root, norm)
    return path if path.is_file() else None


def delete_roadmap_node_hard(root: Path, node_id: str) -> None:
    """Remove a node and its planning sheet in one transaction.

    Raises ``ValueError`` if not found, not removable, or if the resulting graph
    fails validation — in which case nothing is removed from disk.
    """
    from roadmap_chunk_router import validate_callback
    from roadmap_crud_ops import node_index_in_chunk, unknown_node_msg
    from roadmap_crud_prepare import heal_before_mutation

    heal_before_mutation(root)
    chunk = find_chunk_path(root, node_id)
    if not chunk:
        raise ValueError(unknown_node_msg(node_id))
    if chunk.suffix.lower() != ".json":
        raise ValueError(f"unsupported chunk type {chunk.suffix}")
    nodes = load_json_chunk(chunk)
    idx = node_index_in_chunk(nodes, node_id)
    if idx is None:
        raise ValueError(f"node {node_id!r} not found")
    ok, msg = can_hard_remove(root, node_id)
    if not ok:
        raise ValueError(msg)
    removed = nodes[idx]
    sheet = planning_sheet_delete_plan(root, removed.get("planning_dir"))
    del nodes[idx]
    plan = AtomicWritePlan(root=root)
    plan.stage_chunk(chunk, nodes)
    if sheet is not None:
        plan.stage_delete(sheet)
    plan.commit(validate_callback(root))


def cmd_archive(args: object) -> None:
    from roadmap_crud_ops import repo_root

    root = repo_root(args)
    nid = args.node_id
    if args.hard_remove:
        try:
            delete_roadmap_node_hard(root, nid)
        except ValueError as e:
            print(f"error: {e}", file=sys.stderr)
            raise SystemExit(1) from None
        print(f"[ok] removed {nid}")
        return
    print(
        "error: archive-node without --hard-remove is no longer supported "
        "(Cancelled was removed from the roadmap schema).\n"
        "  To retire completed work reversibly, use the archive feature instead:\n"
        "    specy-road archive <NODE_ID>       (restore with: restore-archive)\n"
        "  To delete a node outright, pass --hard-remove after team agreement, "
        "or edit the JSON chunk.",
        file=sys.stderr,
    )
    raise SystemExit(1)
