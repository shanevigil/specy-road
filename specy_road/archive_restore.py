"""Bring an archived subtree back into the live roadmap.

The inverse of :mod:`specy_road.archive_ops`. Because archiving never touched
any live node's ``dependencies`` — the index stands in as the satisfied-key
ledger instead — restoring is a file move plus a manifest edit. No edge
rewriting, no key remapping.

Placement replays the record's ``sources``: every node goes back to the chunk
and array position it came from, so an archive/restore round trip leaves no
diff even when the subtree spanned several chunks or shared one with live work.
"""

from __future__ import annotations

import shutil
from collections import defaultdict
from pathlib import Path
from typing import Any

from specy_road.archive_index import (
    archive_planning_dir,
    find_record,
    load_archive_index,
    write_archive_index,
)
from specy_road.archive_plan import ensure_bundled_scripts_on_path


def _reinsert(existing: list[dict], placements: list[tuple[int, dict]]) -> list[dict]:
    """Put each ``(index, node)`` back at its recorded slot.

    Ascending index order matters: inserting low-to-high means each earlier
    insertion has already shifted the list to make the next index correct. An
    index past the end (the chunk shrank meanwhile) appends instead of failing.
    """
    out = list(existing)
    for idx, node in sorted(placements, key=lambda t: t[0]):
        out.insert(min(idx, len(out)), node)
    return out


def _group_placements(
    record: dict[str, Any], nodes: list[dict]
) -> dict[str, list[tuple[int, dict]]]:
    """Map chunk path -> ``[(index, node)]`` using the record's ``sources``."""
    by_key = {
        n["node_key"]: n for n in nodes if isinstance(n.get("node_key"), str)
    }
    grouped: dict[str, list[tuple[int, dict]]] = defaultdict(list)
    placed: set[str] = set()
    for src in record.get("sources") or []:
        if not isinstance(src, dict):
            continue
        key, chunk, idx = src.get("node_key"), src.get("chunk"), src.get("index")
        node = by_key.get(key) if isinstance(key, str) else None
        if node is None or not isinstance(chunk, str) or not isinstance(idx, int):
            continue
        grouped[chunk].append((idx, node))
        placed.add(key)

    # Records written before `sources` existed, or nodes whose source entry went
    # missing, still have to land somewhere rather than vanish on restore.
    orphans = [n for k, n in by_key.items() if k not in placed]
    if orphans:
        fallback = f"phases/{record['archive_id']}.json"
        grouped[fallback].extend((len(nodes) + i, n) for i, n in enumerate(orphans))
    return dict(grouped)


def _restore_planning_sheets(root: Path, record: dict[str, Any]) -> None:
    for move in record.get("planning") or []:
        if not isinstance(move, dict):
            continue
        stored = (root / str(move.get("stored", ""))).resolve()
        origin = (root / str(move.get("origin", ""))).resolve()
        if not stored.is_file():
            continue
        origin.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(stored), str(origin))


def _write_back(root: Path, grouped: dict[str, list[tuple[int, dict]]]) -> list[str]:
    """Write each target chunk and return the ones needing a manifest include."""
    ensure_bundled_scripts_on_path()
    from roadmap_chunk_utils import load_json_chunk, roadmap_dir, write_json_chunk

    base = roadmap_dir(root)
    need_include: list[str] = []
    for rel, placements in sorted(grouped.items()):
        target = (base / rel).resolve()
        existing = load_json_chunk(target) if target.is_file() else []
        if not target.is_file():
            need_include.append(rel)
        target.parent.mkdir(parents=True, exist_ok=True)
        write_json_chunk(target, _reinsert(existing, placements))
    return need_include


def _sync_includes(root: Path, rels: list[str]) -> None:
    """Add any chunk the restore recreated back into ``manifest.json``."""
    ensure_bundled_scripts_on_path()
    from roadmap_chunk_router_pick import insert_include_in_manifest
    from roadmap_chunk_utils import (
        load_manifest_mapping,
        manifest_path,
        write_manifest,
    )

    manifest = load_manifest_mapping(root)
    before = list(manifest.get("includes") or [])
    for rel in rels:
        insert_include_in_manifest(manifest, rel, rel)
    if list(manifest.get("includes") or []) != before:
        write_manifest(manifest_path(root), manifest)


def _prune_empty_archive(root: Path, doc: dict[str, Any]) -> None:
    """Remove ``roadmap/archive/`` once the last record is restored.

    Archiving and immediately restoring should be net-zero. Leaving an empty
    ledger behind means a user who changed their mind still has a stray file to
    explain in review — and, if it was already committed, a tracked file that
    no longer records anything.
    """
    from specy_road.archive_index import archive_dir, archive_index_path

    if doc.get("records"):
        return
    base = archive_dir(root)
    index = archive_index_path(root)
    leftovers = [p for p in base.rglob("*") if p.is_file() and p != index]
    if leftovers:
        return
    index.unlink(missing_ok=True)
    for d in sorted(base.rglob("*"), reverse=True):
        if d.is_dir():
            d.rmdir()
    base.rmdir()


def restore_archive(root: Path, archive_id: str) -> dict[str, Any]:
    """Restore ``archive_id`` to the live roadmap and drop it from the index.

    A deep archive must be unpacked to shallow first; this refuses rather than
    guessing, so the caller can surface the two-step nature of the operation.
    """
    ensure_bundled_scripts_on_path()
    from roadmap_chunk_utils import load_json_chunk
    from roadmap_crud_ops import run_validate_raise

    doc = load_archive_index(root)
    record = find_record(doc, archive_id)
    if record is None:
        raise ValueError(
            f"no archive with id {archive_id!r} (try: specy-road list-archives)"
        )
    if record.get("depth") == "deep":
        # Unpack first, then fall through to the ordinary shallow restore.
        # Making the caller run two commands buys nothing: the checksum guard
        # lives in undeepen_archive either way, and a refusal there aborts
        # before anything touches the live roadmap.
        from specy_road.archive_deep import undeepen_archive

        undeepen_archive(root, archive_id)
        doc = load_archive_index(root)
        record = find_record(doc, archive_id)
        if record is None:  # pragma: no cover - undeepen would have raised
            raise ValueError(f"archive {archive_id} vanished while unpacking")

    chunk_rel = record.get("chunk")
    if not isinstance(chunk_rel, str) or not (root / chunk_rel).is_file():
        raise ValueError(
            f"archive {archive_id} references chunk {chunk_rel!r}, which is "
            "missing. The archive index and roadmap/archive/ are out of sync."
        )

    src = (root / chunk_rel).resolve()
    nodes = load_json_chunk(src)
    grouped = _group_placements(record, nodes)
    _sync_includes(root, _write_back(root, grouped))
    _restore_planning_sheets(root, record)

    # Validate BEFORE removing the archive. The archived chunk is not in
    # `includes`, so the graph being validated is exactly the restored one, and
    # the still-present ledger only makes archived keys resolvable — which
    # cannot mask a problem. If this raises, the archive is still fully intact
    # and the operator can retry or investigate; deleting first would destroy
    # the only copy on the way to reporting the error.
    run_validate_raise(root)

    src.unlink(missing_ok=True)
    shutil.rmtree(archive_planning_dir(root, archive_id), ignore_errors=True)

    doc["records"] = [
        r for r in doc.get("records", []) if r.get("archive_id") != archive_id
    ]
    write_archive_index(root, doc)
    _prune_empty_archive(root, doc)
    return {
        "archive_id": archive_id,
        "chunks": sorted(grouped),
        "nodes": len(nodes),
    }
