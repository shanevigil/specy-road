"""Deep archive: fold a shallow archive into one capsule file and leave a reference.

The shallow tier keeps archived nodes on disk as readable JSON, which the PM
GUI can still browse. The deep tier is for work nobody expects to look at again:
the chunk and its planning sheets are folded into a single **capsule** —
``roadmap/archive/deep/<archive_id>.json`` — the loose files are removed, and
what stays behind is a small reference file naming the nodes and the git refs
they were delivered on.

**The capsule is text, not an archive format.** The win being bought here is
file-count consolidation: a long-running roadmap accumulates thousands of tiny
planning sheets, and folding each archive into one file keeps that in hand.
Compression is *not* part of it, deliberately. Git already zlib-compresses every
blob and delta-compresses across revisions, so a ``.tar.gz`` here would be an
opaque blob git could not delta — stored in full on every change, with ``diff``,
``blame``, ``log -p`` and ``git grep`` all lost on exactly the content someone
would later want to read. A capsule instead stays greppable, reviewable in a
pull request, and cheap for git to store.

It also makes the checksum mean something. The capsule is written with the same
canonical dump the index uses (``indent=2``, ``sort_keys=True``, trailing
newline), so it is byte-identical every time it is written from the same
content, and its ``sha256`` is reproducible.

The index record survives deepening with its ``node_keys`` and ``nodes_summary``
intact, so archived dependencies stay resolvable and the archive is still
listable without opening the capsule.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from specy_road.archive_index import (
    archive_chunks_dir,
    archive_deep_dir,
    archive_planning_dir,
    archive_refs_dir,
    find_record,
    load_archive_index,
    write_archive_index,
)
from specy_road.roadmap_json import render_canonical_json

CAPSULE_VERSION = 1

# The pre-release deep tier wrote gzipped tarballs. That format never shipped in
# a release, so no reader is kept for it — but a bundle left on disk by a WIP
# checkout should say so plainly rather than fail on a JSON parse error.
_LEGACY_BUNDLE_SUFFIX = ".tar.gz"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _rel(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def build_reference(record: dict[str, Any]) -> dict[str, Any]:
    """The human-readable ref file left behind after deepening.

    Deliberately standalone: it answers "what was this, and where did it land?"
    without the index, the capsule, or a working git remote.
    """
    return {
        "archive_id": record["archive_id"],
        "root_node_id": record["root_node_id"],
        "root_node_key": record["root_node_key"],
        "archived_at": record.get("archived_at"),
        "nodes": record.get("nodes_summary") or [],
        "git": record.get("git") or {},
        "bundle": record.get("bundle") or {},
        "note": (
            "Deep-archived roadmap subtree. Restore with: "
            f"specy-road restore-archive {record['archive_id']}"
        ),
    }


def render_capsule(capsule: dict[str, Any]) -> str:
    """Canonical capsule text — the reason a capsule's ``sha256`` is stable."""
    return render_canonical_json(capsule)


def build_capsule(root: Path, record: dict[str, Any]) -> dict[str, Any] | None:
    """Fold a shallow archive's chunk and sheets into one document.

    ``None`` when nothing is left on disk to fold, which means the index and
    ``roadmap/archive/`` have drifted apart.
    """

    from specy_road.bundled_scripts.roadmap_chunk_utils import load_json_chunk

    chunk = record.get("chunk")
    chunk_path = root / chunk if isinstance(chunk, str) else None
    if chunk_path is None or not chunk_path.is_file():
        return None

    sheets: list[dict[str, str]] = []
    for move in record.get("planning") or []:
        if not isinstance(move, dict):
            continue
        stored = root / str(move.get("stored", ""))
        origin = str(move.get("origin", "")).strip()
        if not origin or not stored.is_file():
            continue
        sheets.append({"origin": origin, "body": stored.read_text(encoding="utf-8")})

    return {
        "capsule_version": CAPSULE_VERSION,
        "archive_id": record["archive_id"],
        "nodes": load_json_chunk(chunk_path),
        # Sorted so the capsule does not depend on the index's list order.
        "planning": sorted(sheets, key=lambda s: s["origin"]),
    }


def _loose_files(root: Path, record: dict[str, Any]) -> list[Path]:
    """Everything the capsule now supersedes, for removal after it is written."""
    out: list[Path] = []
    chunk = record.get("chunk")
    if isinstance(chunk, str) and (root / chunk).is_file():
        out.append((root / chunk).resolve())
    for move in record.get("planning") or []:
        if isinstance(move, dict):
            stored = root / str(move.get("stored", ""))
            if stored.is_file():
                out.append(stored.resolve())
    return out


def deepen_archive(root: Path, archive_id: str) -> dict[str, Any]:
    """Fold a shallow archive into ``archive/deep/`` and write its ref file."""
    doc = load_archive_index(root)
    record = find_record(doc, archive_id)
    if record is None:
        raise ValueError(
            f"no archive with id {archive_id!r} (try: specy-road list-archives)"
        )
    if record.get("depth") == "deep":
        raise ValueError(f"archive {archive_id} is already deep-archived")

    capsule = build_capsule(root, record)
    if capsule is None:
        raise ValueError(
            f"archive {archive_id} has no files left to fold — the index and "
            "roadmap/archive/ are out of sync."
        )
    superseded = _loose_files(root, record)

    deep_dir = archive_deep_dir(root)
    deep_dir.mkdir(parents=True, exist_ok=True)
    path = deep_dir / f"{archive_id}.json"
    path.write_text(render_capsule(capsule), encoding="utf-8")

    record["bundle"] = {"path": _rel(root, path), "sha256": sha256_file(path)}
    record["depth"] = "deep"
    record["chunk"] = None
    record["planning"] = []

    refs_dir = archive_refs_dir(root)
    refs_dir.mkdir(parents=True, exist_ok=True)
    ref_path = refs_dir / f"{archive_id}.json"
    ref_path.write_text(
        render_canonical_json(build_reference(record)), encoding="utf-8"
    )

    # Only now remove the loose files: if anything above failed, the shallow
    # archive is still intact and the operation is simply retryable.
    for src in superseded:
        src.unlink(missing_ok=True)
    shutil.rmtree(archive_planning_dir(root, archive_id), ignore_errors=True)

    write_archive_index(root, doc)
    return record


def _read_capsule(path: Path, archive_id: str) -> dict[str, Any]:
    try:
        capsule = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise ValueError(f"capsule for {archive_id} is not readable JSON ({e})") from e
    if not isinstance(capsule, dict) or not isinstance(capsule.get("nodes"), list):
        raise ValueError(f"capsule for {archive_id} has no roadmap nodes")
    return capsule


def undeepen_archive(root: Path, archive_id: str) -> dict[str, Any]:
    """Unfold a deep archive back to the shallow tier.

    Verifies the capsule checksum first. A capsule that does not match what was
    recorded is not unfolded at all — restoring silently-altered roadmap nodes
    would be worse than refusing.
    """

    from specy_road.bundled_scripts.roadmap_chunk_utils import write_json_chunk

    doc = load_archive_index(root)
    record = find_record(doc, archive_id)
    if record is None:
        raise ValueError(f"no archive with id {archive_id!r}")
    if record.get("depth") != "deep":
        raise ValueError(f"archive {archive_id} is not deep-archived")

    info = record.get("bundle") or {}
    rel = str(info.get("path", ""))
    if rel.endswith(_LEGACY_BUNDLE_SUFFIX):
        raise ValueError(
            f"archive {archive_id} uses the pre-release tar deep-archive format "
            f"({rel}), which specy-road no longer reads. Check out the commit "
            "that wrote it and run `specy-road restore-archive` there, or unpack "
            "the tarball by hand into roadmap/archive/."
        )
    bundle = root / rel
    if not bundle.is_file():
        raise ValueError(
            f"archive {archive_id} references capsule {info.get('path')!r}, "
            "which is missing."
        )
    actual = sha256_file(bundle)
    if actual != info.get("sha256"):
        raise ValueError(
            f"capsule for {archive_id} failed its checksum "
            f"(recorded {str(info.get('sha256'))[:12]}…, found {actual[:12]}…). "
            "Refusing to unfold a modified archive."
        )

    capsule = _read_capsule(bundle, archive_id)

    chunks_dir = archive_chunks_dir(root)
    chunks_dir.mkdir(parents=True, exist_ok=True)
    chunk_path = chunks_dir / f"{archive_id}.json"
    write_json_chunk(chunk_path, list(capsule["nodes"]))

    record["chunk"] = _rel(root, chunk_path)
    record["planning"] = _restore_planning(root, archive_id, capsule)
    record["depth"] = "shallow"
    record["bundle"] = None
    bundle.unlink(missing_ok=True)
    (archive_refs_dir(root) / f"{archive_id}.json").unlink(missing_ok=True)
    write_archive_index(root, doc)
    return record


def _restore_planning(
    root: Path, archive_id: str, capsule: dict[str, Any]
) -> list[dict[str, str]]:
    """Write the capsule's sheets back into the archive's planning directory.

    The capsule carries each sheet's ``origin`` verbatim, so restore puts it
    back exactly where it came from rather than reconstructing the path from
    the filename.
    """
    entries = [s for s in capsule.get("planning") or [] if isinstance(s, dict)]
    if not entries:
        return []
    dest_dir = archive_planning_dir(root, archive_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    moves: list[dict[str, str]] = []
    for sheet in entries:
        origin = str(sheet.get("origin", "")).strip()
        if not origin:
            continue
        dest = dest_dir / Path(origin).name
        dest.write_text(str(sheet.get("body", "")), encoding="utf-8")
        moves.append({"origin": origin, "stored": _rel(root, dest)})
    return moves
