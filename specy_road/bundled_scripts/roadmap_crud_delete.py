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

import contextlib
import os
import shutil
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path

from specy_road.bundled_scripts.planning_artifacts import normalize_planning_dir, resolve_planning_path
from specy_road.bundled_scripts.roadmap_chunk_atomic import AtomicWritePlan
from specy_road.bundled_scripts.roadmap_chunk_utils import find_chunk_path, load_json_chunk
from specy_road.bundled_scripts.roadmap_gui_lib import registry_by_node_id
from specy_road.bundled_scripts.roadmap_load import load_roadmap
from specy_road.registry_yaml import read_registry, registry_path

_GRAPH_TOPS = frozenset({"roadmap", "planning"})


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


def _scratch_target(resolved: Path, scratch: Path, live: Path) -> Path | None:
    """Scratch copy of live graph-tree path ``resolved``, or ``None`` outside the graph trees."""
    for top in _GRAPH_TOPS:
        try:
            return scratch / top / resolved.relative_to((live / top).resolve())
        except ValueError:
            continue
    return None


def _rebase_graph_symlinks(scratch: Path, live: Path) -> None:
    """Point symlinks in the copied graph trees at their scratch counterparts.

    ``copytree(..., symlinks=True)`` keeps links resolving into the live repo, so
    rehearsal would read (and could write) live files, or reject them as outside
    ``roadmap/``. Each link, file or directory, into a live graph tree is
    re-pointed at the same path in the scratch copy, so the layout matches what
    real removal sees. Other links are kept: they resolve outside the scratch
    root, which every chunk lookup, sheet lookup and write rejects, just as live
    removal refuses (or fails validation on) them.
    """
    scratch = scratch.resolve()
    live = live.resolve()
    for top in _GRAPH_TOPS:
        for dirpath, dirnames, filenames in os.walk(scratch / top):
            for name in (*dirnames, *filenames):
                link = Path(dirpath) / name
                if not link.is_symlink():
                    continue
                resolved = link.resolve()
                if resolved == scratch or scratch in resolved.parents:
                    continue
                dst = _scratch_target(resolved, scratch, live)
                if dst is not None:
                    link.unlink()
                    link.symlink_to(dst, target_is_directory=resolved.is_dir())


@contextlib.contextmanager
def rehearsal_root(root: Path) -> Iterator[Path]:
    """Throwaway project root for ``--dry-run``: graph trees copied, the rest linked.

    The live ``root`` is never written. Graph-tree symlinks into the repo are
    rebased onto the scratch copy so rehearsal matches real removal on the same
    layout (see :func:`_rebase_graph_symlinks`).
    """
    with tempfile.TemporaryDirectory(prefix="specy-road-remove-") as tmp:
        scratch = Path(tmp)
        live = root.resolve()
        for entry in live.iterdir():
            if entry.name == ".git":
                continue
            dst = scratch / entry.name
            if entry.name not in _GRAPH_TOPS:
                try:
                    dst.symlink_to(entry, target_is_directory=entry.is_dir())
                    continue
                except OSError:
                    pass
            if entry.is_dir():
                shutil.copytree(entry, dst, symlinks=True)
            elif entry.is_file():
                shutil.copy2(entry, dst)
        _rebase_graph_symlinks(scratch, live)
        yield scratch


def _commit_remove(root: Path, node_id: str) -> Path | None:
    """Apply one removal on ``root``; return the planning sheet path if any."""
    from specy_road.bundled_scripts.roadmap_chunk_router import validate_callback
    from specy_road.bundled_scripts.roadmap_crud_ops import node_index_in_chunk, unknown_node_msg

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
    nodes_after = list(nodes)
    del nodes_after[idx]
    plan = AtomicWritePlan(root=root)
    plan.stage_chunk(chunk, nodes_after)
    if sheet is not None:
        plan.stage_delete(sheet)
    plan.commit(validate_callback(root))
    return sheet


def remove_roadmap_node(root: Path, node_id: str, *, dry_run: bool = False) -> None:
    """Remove a never-started leaf and its planning sheet when nothing blocks it.

    Eligibility is checked on the live graph with no self-heal pass. Real removal
    commits through :class:`~specy_road.bundled_scripts.roadmap_chunk_atomic.AtomicWritePlan`.
    ``--dry-run`` rehearses the same commit on :func:`rehearsal_root` so the live
    tree is not written or unlinked; graph-tree symlinks into the repo are rebased
    onto the scratch copy before rehearsal.

    Raises ``ValueError`` if not found, not removable, or if the resulting graph
    fails validation.
    """
    if dry_run:
        sheet = planning_sheet_delete_plan(
            root,
            next(
                (
                    n.get("planning_dir")
                    for n in load_roadmap(root)["nodes"]
                    if n.get("id") == node_id
                ),
                None,
            ),
        )
        with rehearsal_root(root) as scratch:
            _commit_remove(scratch, node_id)
        print(f"would remove node {node_id}")
        if sheet is not None:
            print(f"planning sheet: {sheet.relative_to(root).as_posix()}")
        else:
            print("planning sheet: (none)")
        return
    _commit_remove(root, node_id)


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
