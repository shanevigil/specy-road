"""Load merged roadmap graph from ``roadmap/manifest.json`` and JSON chunk files."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

from roadmap_chunk_utils import (
    discover_manifest_path,
    load_chunk_nodes,
    load_json_chunk,
    load_manifest_mapping,
)
from specy_road.runtime_paths import default_user_repo_root


# Status precedence used to aggregate non-leaf rollup status. Higher rank =
# "more progressed" / "worth showing first" on mixed subtrees.
#
# Policy from F-013:
#   - Leaf rollup_status == the leaf's own status.
#   - Non-leaf rollup_status == "Complete" iff every leaf descendant rolls up
#     to "Complete"; otherwise the highest-precedence status among leaf
#     descendants. "Blocked" beats "In Progress" so blocked work is visible.
_STATUS_PRECEDENCE = {
    "Not Started": 0,
    "In Progress": 1,
    "Blocked": 2,
    "Complete": 3,
}
_UNKNOWN_STATUS_RANK = -1


def _rank(status: str | None) -> int:
    if not isinstance(status, str):
        return _UNKNOWN_STATUS_RANK
    return _STATUS_PRECEDENCE.get(status, _UNKNOWN_STATUS_RANK)


def _children_map(nodes: list[dict]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for n in nodes:
        pid = n.get("parent_id")
        if isinstance(pid, str) and pid:
            out.setdefault(pid, []).append(n["id"])
    return out


def compute_rollup_status(nodes: list[dict]) -> dict[str, str]:
    """
    Return ``{node_id: rollup_status}`` for every node.

    Leaf rollup is the node's own ``status``. Non-leaf rollup is ``Complete``
    when every leaf descendant is ``Complete``, else the highest-precedence
    status among leaf descendants (``Blocked`` > ``In Progress`` >
    ``Not Started``). Nodes with unknown/invalid status contribute as
    ``Not Started``.
    """
    by_id = {n["id"]: n for n in nodes if isinstance(n.get("id"), str)}
    children = _children_map(nodes)
    cache: dict[str, str] = {}

    def leaf_statuses(nid: str) -> list[str]:
        kids = children.get(nid, [])
        if not kids:
            s = by_id.get(nid, {}).get("status")
            return [s if isinstance(s, str) else "Not Started"]
        out: list[str] = []
        for k in kids:
            out.extend(leaf_statuses(k))
        return out

    for nid in by_id:
        kids = children.get(nid, [])
        if not kids:
            s = by_id[nid].get("status")
            cache[nid] = s if isinstance(s, str) else "Not Started"
            continue
        descendants = leaf_statuses(nid)
        if descendants and all(s == "Complete" for s in descendants):
            cache[nid] = "Complete"
            continue
        # Pick the highest-precedence status among leaf descendants, excluding
        # the "Complete" pile (since not all are Complete, mark with the most
        # pressing not-yet-Complete status).
        non_complete = [s for s in descendants if s != "Complete"]
        if not non_complete:
            # Shouldn't happen given the previous branch, but defensive.
            cache[nid] = "Complete"
            continue
        best = max(non_complete, key=_rank)
        cache[nid] = best
    return cache


def annotate_rollup_status(nodes: list[dict]) -> list[dict]:
    """Attach ``rollup_status`` in place on every node and return the list."""
    rs = compute_rollup_status(nodes)
    for n in nodes:
        nid = n.get("id")
        if isinstance(nid, str) and nid in rs:
            n["rollup_status"] = rs[nid]
    return nodes


def line_count(path: Path) -> int:
    text = path.read_text(encoding="utf-8", errors="replace")
    if not text:
        return 0
    return text.count("\n") + (0 if text.endswith("\n") else 1)


def _fail(msg: str) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(1)


def _read_chunk_nodes(base: Path, rel: str) -> list[dict]:
    if not isinstance(rel, str) or not rel.strip():
        _fail("manifest: each include must be a non-empty string")
    chunk_path = (base / rel).resolve()
    try:
        chunk_path.relative_to(base)
    except ValueError:
        _fail(f"roadmap: invalid include path (outside roadmap/): {rel}")
    if not chunk_path.is_file():
        _fail(f"roadmap: missing include file: {chunk_path}")
    return load_chunk_nodes(chunk_path)


def _merge_includes(root: Path, version: object, includes: list) -> dict:
    base = (root / "roadmap").resolve()
    all_nodes: list[dict] = []
    for rel in includes:
        all_nodes.extend(_read_chunk_nodes(base, rel))
    annotate_rollup_status(all_nodes)
    return {"version": version, "nodes": all_nodes}


def load_roadmap(root: Path | None = None) -> dict:
    """
    Return ``{version, nodes}``. ``manifest.json`` lists ``.json`` chunk paths
    under ``roadmap/`` (merged in ``includes`` order).
    """
    root = root or default_user_repo_root()
    mpath = discover_manifest_path(root)
    doc = load_manifest_mapping(root)
    version = doc.get("version")
    includes = doc.get("includes")
    if "nodes" in doc:
        _fail(
            f"{mpath.relative_to(root)}: top-level `nodes` is not supported; "
            "list chunk files in `includes` (see roadmap/manifest.json).",
        )
    if not isinstance(includes, list):
        _fail(f"{mpath.relative_to(root)}: `includes` must be a list")
    return _merge_includes(root, version, includes)


def _manifest_pure_includes(doc: dict) -> bool:
    inc = doc.get("includes")
    nodes = doc.get("nodes")
    return isinstance(inc, list) and not (isinstance(nodes, list) and len(nodes) > 0)


def _check_oversized_manifest_file(root: Path, path: Path, max_lines: int) -> bool:
    """Return True if violation (manifest should stay a small index)."""
    nlines = line_count(path)
    if nlines <= max_lines:
        return False
    try:
        with path.open(encoding="utf-8") as f:
            doc = json.load(f)
    except (json.JSONDecodeError, OSError):
        print(f"roadmap line limit: {path}: could not parse manifest", file=sys.stderr)
        return True
    if not isinstance(doc, dict):
        return True
    if _manifest_pure_includes(doc):
        print(
            f"roadmap line limit: {path.relative_to(root)}: {nlines} lines "
            f"(max {max_lines}); shorten comments or split chunk files",
            file=sys.stderr,
        )
        return True
    return False


def _roadmap_manifest_max_lines(root: Path) -> int:
    config_path = root / "constraints" / "file-limits.yaml"
    if config_path.is_file():
        with config_path.open(encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        val = cfg.get("roadmap_manifest_max_lines")
        if isinstance(val, int) and val > 0:
            return val
    return 500


def _roadmap_json_chunk_max_lines(root: Path) -> int:
    config_path = root / "constraints" / "file-limits.yaml"
    if config_path.is_file():
        with config_path.open(encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        val = cfg.get("roadmap_json_chunk_max_lines")
        if isinstance(val, int) and val > 0:
            return val
    return 500


def _line_limit_json_chunks(root: Path, base: Path, json_max: int) -> bool:
    failed = False
    for path in sorted(base.rglob("*.json")):
        if path.name == "manifest.json":
            continue
        try:
            path.relative_to(base)
        except ValueError:
            continue
        nlines = line_count(path)
        if nlines <= json_max:
            continue
        try:
            ncount = len(load_json_chunk(path))
        except SystemExit:
            failed = True
            continue
        if ncount != 1:
            print(
                f"roadmap line limit: {path.relative_to(root)}: {nlines} lines "
                f"(max {json_max}); split or reduce to a single node per file",
                file=sys.stderr,
            )
            failed = True
    return failed


def validate_roadmap_line_limits(
    root: Path | None = None, max_lines: int | None = None
) -> None:
    """
    Enforce line counts on roadmap **source** files: ``manifest.json`` and
    ``.json`` chunk files under ``roadmap/``.
    """
    root = root or default_user_repo_root()
    manifest_max = max_lines if max_lines is not None else _roadmap_manifest_max_lines(root)
    json_max = max_lines if max_lines is not None else _roadmap_json_chunk_max_lines(root)
    base = root / "roadmap"
    failed = False
    try:
        mp = discover_manifest_path(root)
        failed = _check_oversized_manifest_file(root, mp, manifest_max)
    except FileNotFoundError:
        print(f"roadmap line limit: missing manifest under {base}", file=sys.stderr)
        failed = True
    failed = _line_limit_json_chunks(root, base, json_max) or failed
    if failed:
        raise SystemExit(1)
