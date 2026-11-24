"""Build a roadmap on disk: manifest, one chunk, planning sheets, registry and git-workflow.yaml."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import yaml

from specy_road.roadmap_chunk_utils import write_json_chunk

_KEYS = uuid.UUID("5e5c7a2d-0c3b-4f6e-9a51-7d0e2b8c4a19")


def node_key(node_id: str) -> str:
    """A node key derived from ``node_id`` alone, so the same id has the same key in every run."""
    return str(uuid.uuid5(_KEYS, node_id))


def roadmap_repo(
    root: Path,
    nodes: list[dict],
    *,
    chunk: str = "phases/M1.json",
    registry: list[dict] | None = None,
    git_workflow: str | None = None,
) -> Path:
    """Write ``nodes`` as the roadmap under ``root`` and return ``root``.

    A node without ``node_key`` gets :func:`node_key` of its id, and one without ``planning_dir``
    gets ``planning/<id>_<codename or unnamed>_<key>.md``; each node's sheet is ``# <id>``.
    ``registry`` is the registry's entries (none by default); ``git_workflow`` is written as
    ``roadmap/git-workflow.yaml`` when given.
    """
    rm = root / "roadmap"
    (rm / chunk).parent.mkdir(parents=True, exist_ok=True)
    written = []
    for given in nodes:
        node = dict(given)
        key = node.setdefault("node_key", node_key(node["id"]))
        slug = node.get("codename") or "unnamed"
        node.setdefault("planning_dir", f"planning/{node['id']}_{slug}_{key}.md")
        sheet = root / node["planning_dir"]
        sheet.parent.mkdir(parents=True, exist_ok=True)
        sheet.write_text(f"# {node['id']}\n", encoding="utf-8")
        written.append(node)
    write_json_chunk(rm / chunk, written)
    manifest = json.dumps({"version": 1, "includes": [chunk]}) + "\n"
    (rm / "manifest.json").write_text(manifest, encoding="utf-8")
    (rm / "registry.yaml").write_text(
        yaml.safe_dump({"version": 1, "entries": registry or []}, sort_keys=False), encoding="utf-8"
    )
    if git_workflow is not None:
        (rm / "git-workflow.yaml").write_text(git_workflow, encoding="utf-8")
    return root
