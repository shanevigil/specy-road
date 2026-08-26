"""Apply a shallow archive: move a completed subtree out of the live roadmap.

The live/archived boundary is ``manifest.json``'s ``includes`` list, which
``roadmap_load`` already treats as authoritative — a chunk file under
``roadmap/`` that no include names is invisible to the loader. So archiving
needs no loader change: write the subtree to ``roadmap/archive/chunks/``, drop
the emptied sources from ``includes``, and the graph shrinks.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from specy_road.archive_index import (
    archive_chunks_dir,
    archive_planning_dir,
    index_records,
    load_archive_index,
    write_archive_index,
)
from specy_road.archive_plan import (
    ArchivePlan,
    build_record,
    ensure_bundled_scripts_on_path,
    plan_archive,
)


def _remove_include(doc: dict[str, Any], rel: str) -> bool:
    includes = doc.get("includes")
    if not isinstance(includes, list) or rel not in includes:
        return False
    doc["includes"] = [x for x in includes if x != rel]
    return True


def _apply_chunk_edits(root: Path, plan: ArchivePlan) -> bool:
    """Rewrite or delete each source chunk. Returns True if the manifest changed."""
    ensure_bundled_scripts_on_path()
    from roadmap_chunk_utils import (
        load_manifest_mapping,
        manifest_path,
        write_json_chunk,
        write_manifest,
    )

    doc = load_manifest_mapping(root)
    changed = False
    for edit in plan.chunk_edits:
        if edit.emptied:
            # Drop the include first: a chunk file that is deleted while still
            # named by an include makes the whole roadmap fail to load.
            changed |= _remove_include(doc, edit.rel)
            edit.path.unlink(missing_ok=True)
        else:
            write_json_chunk(edit.path, list(edit.remaining))
    if changed:
        write_manifest(manifest_path(root), doc)
    return changed


def _move_planning_sheets(root: Path, plan: ArchivePlan) -> list[dict[str, str]]:
    """Move each planning sheet into the archive; skip any that is already gone."""
    from specy_road.archive_plan import planning_moves

    dest_dir = archive_planning_dir(root, plan.archive_id)
    moved: list[dict[str, str]] = []
    for move in planning_moves(plan):
        src = (root / move["origin"]).resolve()
        if not src.is_file():
            continue
        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str((root / move["stored"]).resolve()))
        moved.append(move)
    return moved


def apply_archive(root: Path, plan: ArchivePlan) -> dict[str, Any]:
    """Execute ``plan`` and return the index record it wrote.

    Order matters: the archive chunk is written **before** the sources are
    rewritten, so an interruption leaves a duplicate rather than a hole. The
    index is written last, and validation runs after everything is on disk.
    """
    ensure_bundled_scripts_on_path()
    from roadmap_chunk_utils import write_json_chunk
    from roadmap_crud_ops import run_validate_raise

    chunks_dir = archive_chunks_dir(root)
    chunks_dir.mkdir(parents=True, exist_ok=True)
    chunk_path = chunks_dir / f"{plan.archive_id}.json"
    write_json_chunk(chunk_path, list(plan.nodes))
    chunk_rel = chunk_path.resolve().relative_to(root.resolve()).as_posix()

    _apply_chunk_edits(root, plan)
    moved = _move_planning_sheets(root, plan)

    record = build_record(plan, chunk_rel=chunk_rel)
    record["planning"] = moved
    doc = load_archive_index(root)
    doc.setdefault("records", []).append(record)
    write_archive_index(root, doc)

    run_validate_raise(root)
    return record


def archive_node(
    root: Path, node_id: str, *, force: bool = False
) -> dict[str, Any]:
    """Plan and apply in one step — the ``specy-road archive <NODE_ID>`` path."""
    return apply_archive(root, plan_archive(root, node_id, force=force))


def completed_at(
    root_node: dict[str, Any], activity: dict[str, dict[str, Any]] | None = None
) -> str | None:
    """When this subtree finished, for the auto-archive age threshold.

    ``milestone_execution.closed_at`` is authoritative when present, but only
    milestones that went through a rollup carry it. ``roadmap/activity.json``
    is the fallback: a ``finished`` entry is the moment the node's status
    actually flipped to Complete.
    """
    me = root_node.get("milestone_execution")
    if isinstance(me, dict):
        closed = me.get("closed_at")
        if isinstance(closed, str) and closed.strip():
            return closed.strip()
    if activity:
        entry = activity.get(root_node.get("node_key"))
        if isinstance(entry, dict) and entry.get("kind") in ("finished", "backfilled"):
            at = entry.get("at")
            if isinstance(at, str) and at.strip():
                return at.strip()
    return None


def auto_archive_candidates(
    root: Path, *, older_than_days: int, now_iso: str | None = None
) -> list[tuple[str, str]]:
    """``(node_id, completed_at)`` for subtrees eligible under the age threshold.

    Only the **highest** eligible node in any chain is returned: archiving a
    phase already takes its milestones with it, so offering both would mean
    reporting work twice and then failing on the second archive.
    """
    ensure_bundled_scripts_on_path()
    from datetime import datetime, timedelta, timezone

    from roadmap_load import compute_rollup_status, load_roadmap

    from specy_road.activity_log import activity_by_node_key
    from specy_road.archive_plan import utc_now_iso
    from specy_road.milestone_subtree import subtree_node_ids

    nodes = load_roadmap(root)["nodes"]
    activity = activity_by_node_key(root)
    rollup = compute_rollup_status(nodes)
    now = datetime.fromisoformat(now_iso or utc_now_iso())
    cutoff = now - timedelta(days=max(0, older_than_days))
    archived = {
        k
        for r in index_records(load_archive_index(root))
        for k in r.get("node_keys", [])
    }

    eligible: dict[str, str] = {}
    for n in nodes:
        nid = n.get("id")
        if not isinstance(nid, str) or rollup.get(nid) != "Complete":
            continue
        if n.get("node_key") in archived:
            continue
        done = completed_at(n, activity)
        if not done:
            continue
        try:
            when = datetime.fromisoformat(done)
        except ValueError:
            continue
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        if when <= cutoff:
            eligible[nid] = done

    covered: set[str] = set()
    for nid in eligible:
        covered |= subtree_node_ids(nid, nodes) - {nid}
    return sorted(
        ((nid, done) for nid, done in eligible.items() if nid not in covered),
        key=lambda t: t[0],
    )
