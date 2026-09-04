"""Load merged roadmap nodes from a git ref (git show blobs, no checkout)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from specy_road.git_subprocess import git_ok
from specy_road.registry_remote_overlay_merge import PER_SHOW_TIMEOUT_S
from specy_road.roadmap_json import nodes_from_chunk_doc


def _parse_chunk_json(text: str) -> list[dict[str, Any]] | None:
    """Parse chunk JSON, or ``None`` if it is not a chunk this repo understands."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    nodes = nodes_from_chunk_doc(data)
    if not nodes and isinstance(data, list) and data:
        return None  # a non-empty list holding no objects is not a chunk
    return nodes


def load_roadmap_nodes_at_ref(
    repo_root: Path, ref: str
) -> list[dict[str, Any]] | None:
    """
    Return merged roadmap ``nodes`` at ``ref`` (e.g. ``origin/feature/rm-x``).

    ``None`` if the ref is missing, manifest/chunks unreadable, or parse fails.
    """
    manifest_spec = f"{ref}:roadmap/manifest.json"
    ok, blob = git_ok(["show", manifest_spec], repo_root, PER_SHOW_TIMEOUT_S)
    if not ok or not (blob or "").strip():
        return None
    try:
        doc = json.loads(blob)
    except json.JSONDecodeError:
        return None
    if not isinstance(doc, dict):
        return None
    includes = doc.get("includes")
    if not isinstance(includes, list):
        return None
    all_nodes: list[dict[str, Any]] = []
    base = (repo_root / "roadmap").resolve()
    for rel in includes:
        if not isinstance(rel, str) or not rel.strip():
            continue
        chunk_path = (base / rel).resolve()
        try:
            chunk_path.relative_to(base)
        except ValueError:
            return None
        rel_posix = chunk_path.relative_to(repo_root).as_posix()
        ok_c, chunk_blob = git_ok(
            ["show", f"{ref}:{rel_posix}"],
            repo_root,
            PER_SHOW_TIMEOUT_S,
        )
        if not ok_c or not (chunk_blob or "").strip():
            return None
        nodes = _parse_chunk_json(chunk_blob)
        if nodes is None:
            return None
        all_nodes.extend(nodes)
    return all_nodes
