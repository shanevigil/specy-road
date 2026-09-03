"""Roadmap manifest discovery and JSON chunk loading."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from specy_road.roadmap_json import nodes_from_chunk_doc, render_canonical_json

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


PHASE_PRIMARY_DIR = "phases"

# Why the router created a new chunk, for the operator-facing log line. A phase
# can reach the overflow path too — when its own name is already taken — so the
# node type alone does not identify which rule fired.
PHASE_ROOT_REASON = "phase roots get their own chunk"
OVERFLOW_REASON = "would have overflowed existing chunks"


def phase_root_chunk_rel(root: Path, new_node: dict) -> str | None:
    """Dedicated chunk path for a phase root, e.g. ``phases/M2.json``.

    A phase node has no phase *ancestor*, so the router's locality pass does not
    apply to it and it would otherwise fall through to the capacity-first scan
    and land in whichever chunk had room — typically an unrelated sibling
    phase's file. Everything added under it then follows it there, because the
    chunk lookup for that phase resolves to the same file, so one misrouted
    phase root drags its whole subtree into a misnamed chunk.

    Returns None when the name is unusable or already taken, leaving the caller
    on its normal routing path. "Taken" covers a file that exists on disk but is
    absent from ``includes`` — the state a merge leaves behind when it resolves a
    ``manifest.json`` conflict by dropping an include line. Its nodes are not in
    the merged graph, so writing a fresh chunk over them would destroy them
    without validation noticing anything was lost.
    """
    if new_node.get("type") != "phase":
        return None
    nid = new_node.get("id")
    if not isinstance(nid, str):
        return None
    safe = "".join(c for c in nid.strip() if c.isalnum() or c in "._-")
    if not safe:
        return None
    includes = load_manifest_mapping(root).get("includes") or []
    first = next((x for x in includes if isinstance(x, str) and x.strip()), None)
    parent = Path(first).parent.as_posix() if first else PHASE_PRIMARY_DIR
    rel = f"{safe}.json" if parent in ("", ".") else f"{parent}/{safe}.json"
    if rel in includes or (roadmap_dir(root) / rel).exists():
        return None
    return rel


# Keys that are computed in-memory and must never be persisted to chunk JSON.
_DERIVED_NODE_KEYS = frozenset({"rollup_status"})


def _strip_derived(node: dict) -> dict:
    """Return a shallow copy with computed-only keys removed."""
    return {k: v for k, v in node.items() if k not in _DERIVED_NODE_KEYS}


def render_json_chunk(nodes: list[dict]) -> str:
    """Canonical chunk text (used by both ``write_json_chunk`` and the chunk
    router for line-count prediction without touching disk)."""
    return render_canonical_json({"nodes": [_strip_derived(n) for n in nodes]})


def write_json_chunk(path: Path, nodes: list[dict]) -> None:
    """Write roadmap nodes as canonical ``{"nodes": [...]}`` (stable key order for diffs)."""
    path.write_text(render_json_chunk(nodes), encoding="utf-8")


def render_manifest(doc: dict) -> str:
    """Canonical manifest text.

    Used by the chunk router whenever the manifest is rewritten (auto-routing
    or rebalance). Existing manifests that are never modified keep their
    original on-disk format because the loader is format-agnostic.
    """
    return render_canonical_json(doc)


def write_manifest(path: Path, doc: dict) -> None:
    """Write ``manifest.json`` using :func:`render_manifest` (canonical form)."""
    path.write_text(render_manifest(doc), encoding="utf-8")


def load_json_chunk(path: Path) -> list[dict]:
    """Load nodes from a ``.json`` chunk (single node object, ``nodes`` array, or array)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        _fail_manifest(f"roadmap: JSON parse error in {path}: {e}")
    nodes = nodes_from_chunk_doc(data)
    if nodes is None:
        _fail_manifest(f"roadmap: invalid JSON chunk structure: {path}")
    if not nodes and isinstance(data, list) and data:
        _fail_manifest(f"roadmap: JSON chunk must contain objects: {path}")
    return nodes


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
    gw = base / "git-workflow.yaml"
    if gw.is_file():
        out.append(gw)
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
