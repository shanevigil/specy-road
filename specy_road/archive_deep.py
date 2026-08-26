"""Deep archive: bundle a shallow archive into a tarball and leave a reference.

The shallow tier keeps archived nodes on disk as readable JSON, which the PM
GUI can still browse. The deep tier is for work nobody expects to look at again:
the chunk and its planning sheets are packed into a single ``.tar.gz``, the
loose files are removed, and what stays behind is a small reference file naming
the nodes and the git refs they were delivered on.

The index record survives deepening with its ``node_keys`` and ``nodes_summary``
intact, so archived dependencies stay resolvable and the archive is still
listable without unpacking anything.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tarfile
from pathlib import Path
from typing import Any

from specy_road.archive_index import (
    archive_deep_dir,
    archive_planning_dir,
    archive_refs_dir,
    find_record,
    load_archive_index,
    write_archive_index,
)

# tarfile gained a member-sanitizing extraction filter in 3.12; on 3.11 the
# argument does not exist. Bundles are repo-local and written by this module,
# but a hand-edited one should still not be able to escape the archive dir.
_HAS_EXTRACTION_FILTER = hasattr(tarfile, "data_filter")


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
    without the index, the bundle, or a working git remote.
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


def _bundle_members(root: Path, record: dict[str, Any]) -> list[tuple[Path, str]]:
    """``(absolute path, path inside the tar)`` for everything being packed."""
    members: list[tuple[Path, str]] = []
    chunk = record.get("chunk")
    if isinstance(chunk, str) and (root / chunk).is_file():
        members.append(((root / chunk).resolve(), f"chunk/{Path(chunk).name}"))
    for move in record.get("planning") or []:
        if not isinstance(move, dict):
            continue
        stored = root / str(move.get("stored", ""))
        if stored.is_file():
            members.append((stored.resolve(), f"planning/{stored.name}"))
    return members


def deepen_archive(root: Path, archive_id: str) -> dict[str, Any]:
    """Pack a shallow archive into ``archive/deep/`` and write its ref file."""
    doc = load_archive_index(root)
    record = find_record(doc, archive_id)
    if record is None:
        raise ValueError(
            f"no archive with id {archive_id!r} (try: specy-road list-archives)"
        )
    if record.get("depth") == "deep":
        raise ValueError(f"archive {archive_id} is already deep-archived")

    members = _bundle_members(root, record)
    if not members:
        raise ValueError(
            f"archive {archive_id} has no files left to bundle — the index and "
            "roadmap/archive/ are out of sync."
        )

    deep_dir = archive_deep_dir(root)
    deep_dir.mkdir(parents=True, exist_ok=True)
    bundle = deep_dir / f"{archive_id}.tar.gz"
    with tarfile.open(bundle, "w:gz") as tar:
        for src, arcname in members:
            tar.add(src, arcname=arcname)

    record["bundle"] = {"path": _rel(root, bundle), "sha256": sha256_file(bundle)}
    record["depth"] = "deep"
    record["chunk"] = None
    record["planning"] = []

    refs_dir = archive_refs_dir(root)
    refs_dir.mkdir(parents=True, exist_ok=True)
    ref_path = refs_dir / f"{archive_id}.json"
    ref_path.write_text(
        json.dumps(build_reference(record), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    # Only now remove the loose files: if anything above failed, the shallow
    # archive is still intact and the operation is simply retryable.
    for src, _ in members:
        src.unlink(missing_ok=True)
    shutil.rmtree(archive_planning_dir(root, archive_id), ignore_errors=True)

    write_archive_index(root, doc)
    return record


def _extract(bundle: Path, dest: Path) -> None:
    with tarfile.open(bundle, "r:gz") as tar:
        if _HAS_EXTRACTION_FILTER:
            tar.extractall(dest, filter="data")
        else:  # pragma: no cover - depends on interpreter version
            for member in tar.getmembers():
                target = (dest / member.name).resolve()
                if not str(target).startswith(str(dest.resolve())):
                    raise ValueError(
                        f"refusing bundle member outside the archive: {member.name}"
                    )
            tar.extractall(dest)


def undeepen_archive(root: Path, archive_id: str) -> dict[str, Any]:
    """Unpack a deep archive back to the shallow tier.

    Verifies the bundle checksum first. A bundle that does not match what was
    recorded is not unpacked at all — restoring silently-altered roadmap nodes
    would be worse than refusing.
    """
    doc = load_archive_index(root)
    record = find_record(doc, archive_id)
    if record is None:
        raise ValueError(f"no archive with id {archive_id!r}")
    if record.get("depth") != "deep":
        raise ValueError(f"archive {archive_id} is not deep-archived")

    info = record.get("bundle") or {}
    bundle = root / str(info.get("path", ""))
    if not bundle.is_file():
        raise ValueError(
            f"archive {archive_id} references bundle {info.get('path')!r}, "
            "which is missing."
        )
    actual = sha256_file(bundle)
    if actual != info.get("sha256"):
        raise ValueError(
            f"bundle for {archive_id} failed its checksum "
            f"(recorded {str(info.get('sha256'))[:12]}…, found {actual[:12]}…). "
            "Refusing to unpack a modified archive."
        )

    staging = archive_deep_dir(root) / f".unpack-{archive_id}"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True, exist_ok=True)
    try:
        _extract(bundle, staging)
        record["chunk"] = _restore_chunk(root, archive_id, staging)
        record["planning"] = _restore_planning(root, archive_id, staging)
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    record["depth"] = "shallow"
    record["bundle"] = None
    bundle.unlink(missing_ok=True)
    (archive_refs_dir(root) / f"{archive_id}.json").unlink(missing_ok=True)
    write_archive_index(root, doc)
    return record


def _restore_chunk(root: Path, archive_id: str, staging: Path) -> str:
    from specy_road.archive_index import archive_chunks_dir

    src = next(iter(sorted((staging / "chunk").glob("*.json"))), None)
    if src is None:
        raise ValueError(f"bundle for {archive_id} contains no roadmap chunk")
    chunks_dir = archive_chunks_dir(root)
    chunks_dir.mkdir(parents=True, exist_ok=True)
    dest = chunks_dir / src.name
    shutil.move(str(src), str(dest))
    return _rel(root, dest)


def _restore_planning(
    root: Path, archive_id: str, staging: Path
) -> list[dict[str, str]]:
    """Put sheets back in the archive and rebuild their origin mapping.

    ``planning`` was emptied when the archive was deepened, so the origin path
    is reconstructed from the filename — which is exactly what a live
    ``planning_dir`` looks like, since the flat-planning rule guarantees it.
    """
    src_dir = staging / "planning"
    if not src_dir.is_dir():
        return []
    dest_dir = archive_planning_dir(root, archive_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    moves: list[dict[str, str]] = []
    for src in sorted(src_dir.glob("*.md")):
        dest = dest_dir / src.name
        shutil.move(str(src), str(dest))
        moves.append({"origin": f"planning/{src.name}", "stored": _rel(root, dest)})
    return moves
