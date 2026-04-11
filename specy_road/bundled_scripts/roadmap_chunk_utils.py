"""Roadmap manifest discovery and JSON chunk loading."""

from __future__ import annotations

import json
import sys
from pathlib import Path

MANIFEST_JSON = "manifest.json"


def roadmap_dir(root: Path) -> Path:
    return (root / "roadmap").resolve()


def discover_manifest_path(root: Path) -> Path:
    """Return ``roadmap/manifest.json`` if present."""
    base = roadmap_dir(root)
    j = base / MANIFEST_JSON
    if j.is_file():
        return j
    raise FileNotFoundError(f"no roadmap manifest: expected {j}")


def manifest_path(root: Path) -> Path:
    """Resolved manifest path (same as ``discover_manifest_path``)."""
    return discover_manifest_path(root)


def _fail_manifest(msg: str) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(1)


def load_manifest_mapping(root: Path) -> dict:
    """Load ``manifest.json`` as a mapping (``version``, ``includes``)."""
    path = discover_manifest_path(root)
    with path.open(encoding="utf-8") as f:
        doc = json.load(f)
    if not isinstance(doc, dict):
        _fail_manifest(f"{path.relative_to(root)}: must be a JSON object")
    return doc


def write_json_chunk(path: Path, nodes: list[dict]) -> None:
    """Write roadmap nodes as canonical ``{"nodes": [...]}`` (stable key order for diffs)."""
    body = json.dumps(
        {"nodes": nodes},
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
    )
    if not body.endswith("\n"):
        body += "\n"
    path.write_text(body, encoding="utf-8")


def load_json_chunk(path: Path) -> list[dict]:
    """Load nodes from a ``.json`` chunk (single node object, ``nodes`` array, or array)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        _fail_manifest(f"roadmap: JSON parse error in {path}: {e}")
    if isinstance(data, list):
        out = [n for n in data if isinstance(n, dict)]
        if not out and data:
            _fail_manifest(f"roadmap: JSON chunk must contain objects: {path}")
        return out
    if isinstance(data, dict):
        nodes = data.get("nodes")
        if isinstance(nodes, list):
            return [n for n in nodes if isinstance(n, dict)]
        if "id" in data:
            return [data]
    _fail_manifest(f"roadmap: invalid JSON chunk structure: {path}")


def load_chunk_nodes(path: Path) -> list[dict]:
    """Return node dicts from a ``.json`` chunk file."""
    if path.suffix.lower() == ".json":
        return load_json_chunk(path)
    _fail_manifest(f"roadmap: unsupported chunk type (use .json): {path}")


def iter_roadmap_fingerprint_files(root: Path) -> list[Path]:
    """Paths that should invalidate roadmap GUI cache when modified."""
    base = roadmap_dir(root)
    out: list[Path] = []
    try:
        mp = manifest_path(root)
    except FileNotFoundError:
        return out
    out.append(mp)
    doc = load_manifest_mapping(root)
    for rel in doc.get("includes") or []:
        if not isinstance(rel, str) or not rel.strip():
            continue
        chunk = (base / rel).resolve()
        try:
            chunk.relative_to(base)
        except ValueError:
            continue
        if chunk.is_file():
            out.append(chunk)
    reg = base / "registry.yaml"
    if reg.is_file():
        out.append(reg)
    return sorted(set(out), key=lambda p: str(p))


def find_chunk_path(root: Path, node_id: str) -> Path | None:
    """Chunk file under ``roadmap/`` containing ``node_id``, or None."""
    try:
        path = manifest_path(root)
    except FileNotFoundError:
        return None
    doc = load_manifest_mapping(root)
    includes = doc.get("includes")
    if not includes:
        if any(n.get("id") == node_id for n in load_chunk_nodes(path)):
            return path
        return None
    base = roadmap_dir(root)
    for rel in includes:
        if not isinstance(rel, str):
            continue
        chunk = (base / rel).resolve()
        try:
            chunk.relative_to(base)
        except ValueError:
            continue
        if not chunk.is_file():
            continue
        if any(n.get("id") == node_id for n in load_chunk_nodes(chunk)):
            return chunk
    return None


def build_node_chunk_map(root: Path) -> dict[str, Path]:
    """Map node id to chunk path (last wins; validator rejects duplicate ids)."""
    try:
        path = manifest_path(root)
    except FileNotFoundError:
        return {}
    by_id: dict[str, Path] = {}
    doc = load_manifest_mapping(root)
    includes = doc.get("includes")
    if not includes:
        for n in load_chunk_nodes(path):
            nid = n.get("id")
            if isinstance(nid, str):
                by_id[nid] = path
        return by_id
    base = roadmap_dir(root)
    for rel in includes:
        if not isinstance(rel, str):
            continue
        chunk = (base / rel).resolve()
        try:
            chunk.relative_to(base)
        except ValueError:
            continue
        if not chunk.is_file():
            continue
        for n in load_chunk_nodes(chunk):
            nid = n.get("id")
            if isinstance(nid, str):
                by_id[nid] = chunk
    return by_id


def resolve_chunk_file(root: Path, chunk_arg: str) -> Path:
    """
    Resolve ``chunk_arg`` to an existing file under ``roadmap/``.
    Accepts ``phases/M0.json`` or ``roadmap/phases/M0.json``.
    """
    base = roadmap_dir(root)
    raw = chunk_arg.strip().replace("\\", "/")
    if raw.startswith("roadmap/"):
        raw = raw.removeprefix("roadmap/")
    candidate = (base / raw).resolve()
    try:
        candidate.relative_to(base)
    except ValueError as e:
        raise ValueError(f"chunk path escapes roadmap/: {chunk_arg!r}") from e
    if not candidate.is_file():
        raise FileNotFoundError(f"chunk file not found: {candidate}")
    return candidate
