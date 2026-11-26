"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

from pathlib import Path
from tests.helpers import REPO
from tests.helpers import SCHEMAS
import json
import shutil
from specy_road.roadmap_chunk_utils import write_json_chunk

# Use distinct UUID-shaped prefixes so the 6-hex tail of node_key derived
# filenames differs across nodes (the router takes the first 6 hex chars).
NK = "{tail:08d}-0000-4000-8000-000000000001"

def node(
    nid: str,
    parent: str | None,
    *,
    type_: str = "task",
    title: str = "T",
    codename: str | None = None,
    n_index: int = 1,
    deps: list[str] | None = None,
) -> dict:
    """Shared test helper."""
    nk = NK.format(tail=n_index)
    cn = codename
    if cn is None and type_ == "task":
        cn = f"{title.lower().replace(' ', '-')}-{n_index:03d}"
    pd = (
        f"planning/{nid}_{cn or 'unnamed'}_{nk}.md"
        if type_ in ("phase", "milestone", "task", "vision", "gate")
        else None
    )
    out: dict = {
        "id": nid,
        "node_key": nk,
        "parent_id": parent,
        "type": type_,
        "title": title,
        "codename": cn,
        "planning_dir": pd,
        "execution_milestone": "Agentic-led" if type_ != "phase" else "Human-led",
        "status": "Not Started",
        "touch_zones": [],
        "dependencies": list(deps or []),
        "parallel_tracks": 1,
    }
    return {k: v for k, v in out.items() if v is not None}

def write_planning(root: Path, node: dict) -> None:
    """Shared test helper."""
    pd = node.get("planning_dir")
    if not isinstance(pd, str):
        return
    p = root / pd
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"# {node['id']}\n", encoding="utf-8")

def seed_repo(root: Path, chunks: dict[str, list[dict]]) -> None:
    """Build a minimal-but-complete repo: schemas, constraints, planning, manifest, chunks."""
    shutil.copytree(SCHEMAS, root / "schemas")
    shutil.copytree(REPO / "constraints", root / "constraints")
    (root / "shared").mkdir(parents=True)
    (root / "shared" / "README.md").write_text("# Shared\n", encoding="utf-8")
    (root / "roadmap" / "phases").mkdir(parents=True)
    (root / "roadmap" / "registry.yaml").write_text(
        "version: 1\nentries: []\n", encoding="utf-8"
    )
    includes = list(chunks.keys())
    (root / "roadmap" / "manifest.json").write_text(
        json.dumps({"version": 1, "includes": includes}) + "\n",
        encoding="utf-8",
    )
    pl = root / "planning"
    pl.mkdir(parents=True)
    for rel, nodes in chunks.items():
        write_json_chunk(root / "roadmap" / rel, nodes)
        for n in nodes:
            write_planning(root, n)

def phase_m0(parent: str | None = None) -> dict:
    """Shared test helper."""
    return node("M0", None, type_="phase", title="phase0", codename=None, n_index=1)

def milestone(nid: str, parent: str, *, n_index: int) -> dict:
    """Shared test helper."""
    return node(nid, parent, type_="milestone", title=f"m{n_index}", n_index=n_index)
