"""Load merged roadmap graph from roadmap/roadmap.yaml (inline or includes)."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


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
        _fail("roadmap.yaml: each include must be a non-empty string")
    chunk_path = (base / rel).resolve()
    try:
        chunk_path.relative_to(base)
    except ValueError:
        _fail(f"roadmap: invalid include path (outside roadmap/): {rel}")
    if not chunk_path.is_file():
        _fail(f"roadmap: missing include file: {chunk_path}")
    with chunk_path.open(encoding="utf-8") as cf:
        chunk = yaml.safe_load(cf)
    if not isinstance(chunk, dict) or "nodes" not in chunk:
        _fail(f"roadmap: {rel} must be a mapping with a `nodes` list")
    nodes = chunk["nodes"]
    if not isinstance(nodes, list):
        _fail(f"roadmap: {rel}: `nodes` must be a list")
    return nodes


def _merge_includes(root: Path, version: object, includes: list) -> dict:
    base = (root / "roadmap").resolve()
    all_nodes: list[dict] = []
    for rel in includes:
        all_nodes.extend(_read_chunk_nodes(base, rel))
    return {"version": version, "nodes": all_nodes}


def load_roadmap(root: Path | None = None) -> dict:
    """
    Return ``{version, nodes}``. Legacy: top-level ``nodes``. Split: ``includes``
    lists chunk files under ``roadmap/`` (each file has ``nodes`` only).
    """
    root = root or ROOT
    manifest = root / "roadmap" / "roadmap.yaml"
    if not manifest.is_file():
        raise FileNotFoundError(manifest)
    with manifest.open(encoding="utf-8") as f:
        doc = yaml.safe_load(f)
    if not isinstance(doc, dict):
        _fail("roadmap.yaml must be a mapping")
    version = doc.get("version")
    includes = doc.get("includes")
    top_nodes = doc.get("nodes")
    if includes is not None:
        if not isinstance(includes, list):
            _fail("roadmap.yaml: `includes` must be a list")
        if "nodes" in doc:
            _fail("roadmap.yaml: use either top-level `nodes` or `includes`, not both")
        return _merge_includes(root, version, includes)
    nodes = top_nodes if isinstance(top_nodes, list) else []
    return {"version": version, "nodes": nodes}


def _check_oversized_file(root: Path, path: Path, max_lines: int) -> bool:
    """Return True if violation."""
    nlines = line_count(path)
    if nlines <= max_lines:
        return False
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        print(f"roadmap line limit: {path}: not a mapping", file=sys.stderr)
        return True
    if path.name == "roadmap.yaml" and data.get("includes") is not None and not data.get(
        "nodes"
    ):
        print(
            f"roadmap line limit: {path.relative_to(root)}: {nlines} lines "
            f"(max {max_lines}); split chunk files or shorten comments",
            file=sys.stderr,
        )
        return True
    nodes = data.get("nodes")
    if not isinstance(nodes, list) or len(nodes) != 1:
        print(
            f"roadmap line limit: {path.relative_to(root)}: {nlines} lines "
            f"(max {max_lines}); split into smaller files or reduce to a single "
            f"task/sub-task node per file when above the limit",
            file=sys.stderr,
        )
        return True
    return False


def validate_roadmap_yaml_line_limits(root: Path | None = None, max_lines: int = 400) -> None:
    """
    No roadmap YAML exceeds ``max_lines`` unless it defines exactly one node.
    Skips ``registry.yaml``.
    """
    root = root or ROOT
    base = root / "roadmap"
    failed = False
    for path in sorted(base.rglob("*.yaml")):
        if path.name == "registry.yaml":
            continue
        if _check_oversized_file(root, path, max_lines):
            failed = True
    if failed:
        raise SystemExit(1)
