"""Pure routing decision: choose the chunk that should receive a new node.

No on-disk mutation. The router public entry points in
:mod:`roadmap_chunk_router` consume :func:`pick_target_chunk` to plan
atomic writes.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

import yaml

from roadmap_chunk_utils import (
    build_node_chunk_map,
    load_json_chunk,
    load_manifest_mapping,
    render_json_chunk,
    roadmap_dir,
)


_DEFAULT_MAX_CHUNK_LINES = 500
_NEW_CHUNK_KEY_HEX_DEFAULT = 6
_NEW_CHUNK_KEY_HEX_FALLBACK = 8
_PHASE_PRIMARY_DIR = "phases"


def chunk_max_lines(root: Path) -> int:
    """Resolve ``roadmap_json_chunk_max_lines`` from ``constraints/file-limits.yaml``."""
    cfg_path = root / "constraints" / "file-limits.yaml"
    if not cfg_path.is_file():
        return _DEFAULT_MAX_CHUNK_LINES
    try:
        with cfg_path.open(encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
    except (OSError, yaml.YAMLError):
        return _DEFAULT_MAX_CHUNK_LINES
    val = cfg.get("roadmap_json_chunk_max_lines")
    if isinstance(val, int) and val > 0:
        return val
    return _DEFAULT_MAX_CHUNK_LINES


def simulate_chunk_lines(nodes: list[dict]) -> int:
    """Predict the line count :func:`write_json_chunk` would produce for ``nodes``."""
    text = render_json_chunk(nodes)
    if not text:
        return 0
    return text.count("\n") + (0 if text.endswith("\n") else 1)


def manifest_includes(root: Path) -> list[str]:
    doc = load_manifest_mapping(root)
    inc = doc.get("includes") or []
    return [x for x in inc if isinstance(x, str) and x.strip()]


def load_merged_nodes(root: Path) -> list[dict]:
    """Load merged nodes WITHOUT triggering rollup annotation (cheaper, no validation)."""
    base = roadmap_dir(root)
    out: list[dict] = []
    for rel in manifest_includes(root):
        chunk = (base / rel).resolve()
        try:
            chunk.relative_to(base)
        except ValueError:
            continue
        if chunk.is_file():
            out.extend(load_json_chunk(chunk))
    return out


def all_chunks_in_manifest_order(root: Path) -> list[Path]:
    base = roadmap_dir(root)
    out: list[Path] = []
    for rel in manifest_includes(root):
        chunk = (base / rel).resolve()
        try:
            chunk.relative_to(base)
        except ValueError:
            continue
        if chunk.is_file():
            out.append(chunk)
    return out


def phase_ancestor_id(merged_nodes: list[dict], parent_id: str | None) -> str | None:
    """Walk parent links from ``parent_id`` until a ``phase`` node is found."""
    if parent_id is None:
        return None
    by_id = {n["id"]: n for n in merged_nodes}
    cur = by_id.get(parent_id)
    while cur is not None:
        if cur.get("type") == "phase":
            nid = cur.get("id")
            return nid if isinstance(nid, str) else None
        pid = cur.get("parent_id")
        if not isinstance(pid, str):
            return None
        cur = by_id.get(pid)
    return None


def chunks_holding_phase(root: Path, phase_id: str) -> list[Path]:
    """Chunks (manifest order) holding any node whose nearest phase ancestor is ``phase_id``."""
    merged_nodes = load_merged_nodes(root)
    chunk_map = build_node_chunk_map(root)
    base = roadmap_dir(root)
    includes = manifest_includes(root)
    include_index = {(base / rel).resolve(): i for i, rel in enumerate(includes)}

    matching: set[Path] = set()
    for node in merged_nodes:
        ancestor = phase_ancestor_id(merged_nodes, node.get("parent_id"))
        if node.get("type") == "phase" and node.get("id") == phase_id:
            ancestor = phase_id
        if ancestor != phase_id:
            continue
        nid = node.get("id")
        if not isinstance(nid, str):
            continue
        chunk = chunk_map.get(nid)
        if chunk:
            matching.add(chunk)
    return sorted(matching, key=lambda p: include_index.get(p, len(includes)))


def strip_partN_suffix(stem: str) -> str:
    """Strip a trailing ``__<hex>`` suffix from a chunk stem so we don't accumulate."""
    if "__" in stem:
        head, tail = stem.rsplit("__", 1)
        if tail and all(c in "0123456789abcdefABCDEF" for c in tail):
            return head
    return stem


def _new_chunk_path_for_base(base_rel: str, node_key: str, hex_len: int) -> str:
    p = Path(base_rel)
    parent = p.parent.as_posix()
    stem = strip_partN_suffix(p.stem)
    nk_hex = "".join(c for c in (node_key or "").lower() if c in "0123456789abcdef")
    suffix = nk_hex[:hex_len] if nk_hex else uuid.uuid4().hex[:hex_len]
    fname = f"{stem}__{suffix}.json"
    return f"{parent}/{fname}" if parent and parent != "." else fname


def derive_new_chunk_path(root: Path, base_chunk_rel: str | None, new_node: dict) -> str:
    """Compute a deterministic relative path (under ``roadmap/``) for a brand-new chunk.

    Same ``node_key`` -> same filename; different keys -> different filenames.
    Two PMs concurrently creating overflow chunks on parallel branches pick
    different filenames for different nodes; merging only adds two new
    ``includes`` lines.
    """
    base_rel = (base_chunk_rel or "").strip()
    if not base_rel:
        includes = manifest_includes(root)
        base_rel = includes[0] if includes else f"{_PHASE_PRIMARY_DIR}/M.json"
    node_key = str(new_node.get("node_key") or "")
    cand = _new_chunk_path_for_base(base_rel, node_key, _NEW_CHUNK_KEY_HEX_DEFAULT)
    existing = set(manifest_includes(root))
    if cand in existing:
        cand = _new_chunk_path_for_base(base_rel, node_key, _NEW_CHUNK_KEY_HEX_FALLBACK)
        if cand in existing:
            cand = _new_chunk_path_for_base(
                base_rel, node_key + uuid.uuid4().hex, _NEW_CHUNK_KEY_HEX_FALLBACK
            )
    return cand


def default_chunk_for_parent(root: Path, parent_id: str | None) -> str | None:
    """Find a base chunk path for routing decisions.

    Preference order:
    1. The phase ancestor's own chunk (so overflow chunks accumulate near
       their phase, e.g. ``M3.json`` → ``M3__abc123.json``).
    2. The parent's own chunk (if no phase ancestor — e.g. when the parent
       is itself a phase or a top-level orphan).
    3. The first manifest include (last-resort default).
    """
    merged = load_merged_nodes(root)
    chunk_map = build_node_chunk_map(root)
    base = roadmap_dir(root)
    if parent_id is None:
        includes = manifest_includes(root)
        return includes[0] if includes else None
    phase_id = phase_ancestor_id(merged, parent_id)
    if phase_id:
        ph_chunk = chunk_map.get(phase_id)
        if ph_chunk:
            try:
                return ph_chunk.relative_to(base).as_posix()
            except ValueError:
                pass
    parent_chunk = chunk_map.get(parent_id)
    if parent_chunk:
        try:
            return parent_chunk.relative_to(base).as_posix()
        except ValueError:
            pass
    includes = manifest_includes(root)
    return includes[0] if includes else None


@dataclass
class RoutingDecision:
    """Outcome of :func:`pick_target_chunk`."""

    chunk_path: Path
    is_new_chunk: bool
    nodes_after: list[dict]
    chunk_rel: str


def _try_chunk(
    chunk: Path, new_node: dict, max_lines: int
) -> tuple[list[dict], int] | None:
    nodes = load_json_chunk(chunk) if chunk.is_file() else []
    after = [*nodes, new_node]
    lines = simulate_chunk_lines(after)
    if lines <= max_lines:
        return after, lines
    return None


def _candidates_sorted(
    chunks: list[Path], new_node: dict, max_lines: int
) -> list[tuple[int, int, Path, list[dict]]]:
    out: list[tuple[int, int, Path, list[dict]]] = []
    for idx, chunk in enumerate(chunks):
        result = _try_chunk(chunk, new_node, max_lines)
        if result is not None:
            after, lines_after = result
            out.append((lines_after, idx, chunk, after))
    out.sort(key=lambda t: (t[0], t[1], str(t[2])))
    return out


def _route_via_hint(
    root: Path, hint_chunk_rel: str | None, new_node: dict, max_lines: int
) -> RoutingDecision | None:
    if not hint_chunk_rel:
        return None
    base = roadmap_dir(root)
    hint_clean = hint_chunk_rel.strip().replace("\\", "/").removeprefix("roadmap/")
    if not hint_clean:
        return None
    hint_abs = (base / hint_clean).resolve()
    try:
        hint_abs.relative_to(base)
    except ValueError:
        return None
    if not hint_abs.is_file():
        return None
    result = _try_chunk(hint_abs, new_node, max_lines)
    if result is None:
        return None
    after, _lines = result
    return RoutingDecision(
        chunk_path=hint_abs,
        is_new_chunk=False,
        nodes_after=after,
        chunk_rel=hint_abs.relative_to(base).as_posix(),
    )


def _route_via_existing_chunks(
    root: Path, candidates: list[Path], new_node: dict, max_lines: int
) -> RoutingDecision | None:
    cands = _candidates_sorted(candidates, new_node, max_lines)
    if not cands:
        return None
    _lines, _idx, chunk, after = cands[0]
    base = roadmap_dir(root)
    return RoutingDecision(
        chunk_path=chunk,
        is_new_chunk=False,
        nodes_after=after,
        chunk_rel=chunk.relative_to(base).as_posix(),
    )


def pick_target_chunk(
    root: Path,
    parent_id: str | None,
    hint_chunk_rel: str | None,
    new_node: dict,
    max_lines: int | None = None,
) -> RoutingDecision:
    """Choose the chunk that should receive ``new_node``.

    Priority order (tuned for locality + concurrency-friendliness):

    1. Hint chunk if it still fits.
    2. Smallest valid chunk in the same phase subtree (manifest-order tie-break).
    3. **Auto-create a new chunk in the same phase** when same-phase chunks
       are full. Locality matters: scattering siblings of one phase across
       unrelated phase chunks made parallel-PM merges noisier and made the
       graph less reviewable. The new chunk's filename derives from the new
       node's ``node_key`` so two PMs adding overflow nodes on parallel
       branches generate different filenames and never collide on a chunk
       file (only the manifest gets a clean two-line addition).
    4. Only when there is no phase ancestor (e.g. authoring a vision/phase
       row), fall back to smallest-valid-anywhere then auto-create.
    """
    if max_lines is None:
        max_lines = chunk_max_lines(root)

    decision = _route_via_hint(root, hint_chunk_rel, new_node, max_lines)
    if decision is not None:
        return decision

    merged = load_merged_nodes(root)
    phase_id = phase_ancestor_id(merged, parent_id)
    if phase_id:
        decision = _route_via_existing_chunks(
            root, chunks_holding_phase(root, phase_id), new_node, max_lines
        )
        if decision is not None:
            return decision
        # No same-phase chunk fits → create a new chunk for this phase.
        return _build_new_chunk_decision(root, parent_id, new_node)

    # No phase ancestor: scan all chunks, then create.
    decision = _route_via_existing_chunks(
        root, all_chunks_in_manifest_order(root), new_node, max_lines
    )
    if decision is not None:
        return decision
    return _build_new_chunk_decision(root, parent_id, new_node)


def _build_new_chunk_decision(
    root: Path, parent_id: str | None, new_node: dict
) -> RoutingDecision:
    base = roadmap_dir(root)
    base_rel = default_chunk_for_parent(root, parent_id)
    new_rel = derive_new_chunk_path(root, base_rel, new_node)
    new_abs = (base / new_rel).resolve()
    try:
        new_abs.relative_to(base)
    except ValueError as e:
        raise ValueError(f"derived chunk path escapes roadmap/: {new_rel!r}") from e
    return RoutingDecision(
        chunk_path=new_abs,
        is_new_chunk=True,
        nodes_after=[new_node],
        chunk_rel=new_rel,
    )


def insert_include_in_manifest(
    doc: dict, new_rel: str, base_chunk_rel: str | None
) -> None:
    """Insert ``new_rel`` into ``doc['includes']``; idempotent.

    Insertion point: after the last entry that shares the new chunk's stem
    prefix and parent directory; otherwise append at end.
    """
    includes = doc.setdefault("includes", [])
    if not isinstance(includes, list):
        raise ValueError("manifest 'includes' must be a list")
    if new_rel in includes:
        return
    insert_at = len(includes)
    if base_chunk_rel:
        base_stem = strip_partN_suffix(Path(base_chunk_rel).stem)
        new_parent = Path(new_rel).parent
        for i, rel in enumerate(includes):
            if not isinstance(rel, str):
                continue
            stem = strip_partN_suffix(Path(rel).stem)
            if stem == base_stem and Path(rel).parent == new_parent:
                insert_at = i + 1
    includes.insert(insert_at, new_rel)
