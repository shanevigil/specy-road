"""Node removal for the roadmap CRUD CLI (``remove-node``, ``archive-node --hard-remove``).

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

from specy_road.bundled_scripts.planning_artifacts import normalize_planning_dir, resolve_planning_path
from specy_road.bundled_scripts.roadmap_chunk_atomic import AtomicWritePlan
from specy_road.bundled_scripts.roadmap_chunk_utils import find_chunk_path, load_json_chunk
from specy_road.bundled_scripts.roadmap_gui_lib import registry_by_node_id
from specy_road.bundled_scripts.roadmap_load import load_roadmap
from specy_road.registry_yaml import read_registry, registry_path


def remove_node_blockers(root: Path, node_id: str) -> list[str]:
    """Every reason ``node_id`` cannot be removed with ``remove-node`` / hard-remove."""
    nodes = load_roadmap(root)["nodes"]
    target = next((n for n in nodes if n.get("id") == node_id), None)
    if target is None:
        return []
    target_key = target.get("node_key")
    blockers: list[str] = []
    status = target.get("status")
    if status != "Not Started":
        blockers.append(f"node {node_id} status is {status!r}, not 'Not Started'")
    claim = registry_by_node_id(read_registry(registry_path(root))).get(node_id)
    if claim:
        blockers.append(
            "registry claim "
            f"codename {claim.get('codename')!r}, branch {claim.get('branch')!r}"
        )
    for n in nodes:
        if n.get("parent_id") == node_id:
            blockers.append(f"child node {n['id']} has parent_id {node_id!r}")
        if target_key and target_key in (n.get("dependencies") or []):
            blockers.append(f"node {n['id']} depends on node_key of {node_id!r}")
    return blockers


def can_hard_remove(root: Path, node_id: str) -> tuple[bool, str]:
    """Whether ``node_id`` passes every ``remove-node`` eligibility check."""
    blockers = remove_node_blockers(root, node_id)
    if blockers:
        return False, "\n".join(blockers)
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


def remove_roadmap_node(root: Path, node_id: str, *, dry_run: bool = False) -> None:
    """Remove a never-started leaf and its planning sheet when nothing blocks it.

    Raises ``ValueError`` if not found, not removable, or if the resulting graph
    fails validation — in which case nothing is removed from disk. With
    ``dry_run=True``, runs the same checks and prints what would be removed
    without writing.
    """
    from specy_road.bundled_scripts.roadmap_chunk_router import validate_callback
    from specy_road.bundled_scripts.roadmap_crud_ops import node_index_in_chunk, unknown_node_msg
    from specy_road.bundled_scripts.roadmap_crud_prepare import heal_before_mutation

    chunk = find_chunk_path(root, node_id)
    if not chunk:
        raise ValueError(unknown_node_msg(node_id))
    if chunk.suffix.lower() != ".json":
        raise ValueError(f"unsupported chunk type {chunk.suffix}")
    nodes = load_json_chunk(chunk)
    idx = node_index_in_chunk(nodes, node_id)
    if idx is None:
        raise ValueError(f"node {node_id!r} not found")
    blockers = remove_node_blockers(root, node_id)
    if blockers:
        raise ValueError("\n".join(blockers))
    removed = nodes[idx]
    sheet = planning_sheet_delete_plan(root, removed.get("planning_dir"))
    if dry_run:
        print(f"would remove node {node_id}")
        if sheet is not None:
            print(f"planning sheet: {sheet.relative_to(root).as_posix()}")
        else:
            print("planning sheet: (none)")
        return
    heal_before_mutation(root)
    chunk = find_chunk_path(root, node_id)
    if not chunk:
        raise ValueError(unknown_node_msg(node_id))
    nodes = load_json_chunk(chunk)
    idx = node_index_in_chunk(nodes, node_id)
    if idx is None:
        raise ValueError(f"node {node_id!r} not found")
    removed = nodes[idx]
    sheet = planning_sheet_delete_plan(root, removed.get("planning_dir"))
    del nodes[idx]
    plan = AtomicWritePlan(root=root)
    plan.stage_chunk(chunk, nodes)
    if sheet is not None:
        plan.stage_delete(sheet)
    plan.commit(validate_callback(root))


def delete_roadmap_node_hard(root: Path, node_id: str) -> None:
    """Backward-compatible alias for :func:`remove_roadmap_node` (no dry-run)."""
    remove_roadmap_node(root, node_id, dry_run=False)


def _exit_on_value_error(fn: object, *args: object, **kwargs: object) -> None:
    try:
        fn(*args, **kwargs)  # type: ignore[operator]
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        raise SystemExit(1) from None


def cmd_remove_node(args: object) -> None:
    from specy_road.bundled_scripts.roadmap_crud_ops import repo_root

    root = repo_root(args)
    nid = args.node_id
    dry_run = bool(getattr(args, "dry_run", False))
    _exit_on_value_error(remove_roadmap_node, root, nid, dry_run=dry_run)
    if not dry_run:
        print(f"[ok] removed {nid}")


def cmd_archive(args: object) -> None:
    from specy_road.bundled_scripts.roadmap_crud_ops import repo_root

    root = repo_root(args)
    nid = args.node_id
    if args.hard_remove:
        _exit_on_value_error(remove_roadmap_node, root, nid, dry_run=False)
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
