"""Locate roadmap YAML chunks and load node lists (shared by finish_task, CRUD, list)."""

from __future__ import annotations

from pathlib import Path

import yaml

MANIFEST_NAME = "roadmap.yaml"


def roadmap_dir(root: Path) -> Path:
    return (root / "roadmap").resolve()


def manifest_path(root: Path) -> Path:
    return roadmap_dir(root) / MANIFEST_NAME


def iter_roadmap_yaml_files(root: Path) -> list[Path]:
    """All ``roadmap/**/*.yaml`` except ``registry.yaml``."""
    base = roadmap_dir(root)
    if not base.is_dir():
        return []
    out: list[Path] = []
    for p in sorted(base.rglob("*.yaml")):
        if p.name == "registry.yaml":
            continue
        out.append(p)
    return out


def load_chunk_nodes(path: Path) -> list[dict]:
    """Return ``nodes`` list from a chunk or legacy manifest (empty if missing)."""
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        return []
    nodes = data.get("nodes")
    if not isinstance(nodes, list):
        return []
    return [n for n in nodes if isinstance(n, dict)]


def find_chunk_path(root: Path, node_id: str) -> Path | None:
    """Return the YAML file under ``roadmap/`` that contains ``node_id``, or None."""
    path = manifest_path(root)
    if not path.is_file():
        return None
    with path.open(encoding="utf-8") as f:
        doc = yaml.safe_load(f)
    if not isinstance(doc, dict):
        return None
    includes = doc.get("includes")
    if not includes:
        if any(n.get("id") == node_id for n in load_chunk_nodes(path)):
            return path
        return None
    base = roadmap_dir(root)
    for rel in includes:
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
    """Map node id -> chunk file path (last wins if duplicate; validator catches dupes)."""
    path = manifest_path(root)
    by_id: dict[str, Path] = {}
    if not path.is_file():
        return by_id
    with path.open(encoding="utf-8") as f:
        doc = yaml.safe_load(f)
    if not isinstance(doc, dict):
        return by_id
    includes = doc.get("includes")
    if not includes:
        for n in load_chunk_nodes(path):
            nid = n.get("id")
            if isinstance(nid, str):
                by_id[nid] = path
        return by_id
    base = roadmap_dir(root)
    for rel in includes:
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
    Accepts ``phases/M0.yaml`` or ``roadmap/phases/M0.yaml``.
    """
    base = roadmap_dir(root)
    raw = chunk_arg.strip().replace("\\", "/")
    if raw.startswith("roadmap/"):
        raw = raw[len("roadmap/") :]
    candidate = (base / raw).resolve()
    try:
        candidate.relative_to(base)
    except ValueError as e:
        raise ValueError(f"chunk path escapes roadmap/: {chunk_arg!r}") from e
    if not candidate.is_file():
        raise FileNotFoundError(f"chunk file not found: {candidate}")
    return candidate
