"""Load merged roadmap nodes from a git ref (git show blobs, no checkout)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from specy_road.git_subprocess import git_ok
from specy_road.registry_remote_overlay_merge import PER_SHOW_TIMEOUT_S


def _parse_chunk_json(text: str) -> list[dict[str, Any]] | None:
    """Parse chunk JSON (same shapes as ``load_json_chunk`` on disk)."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if isinstance(data, list):
        out = [n for n in data if isinstance(n, dict)]
        return out if out or not data else None
    if isinstance(data, dict):
        nodes = data.get("nodes")
        if isinstance(nodes, list):
            return [n for n in nodes if isinstance(n, dict)]
        if "id" in data:
            return [data]
    return None


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
