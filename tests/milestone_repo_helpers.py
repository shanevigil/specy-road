"""A git repo with milestone ``M2`` over leaves ``M2.1`` (alpha) and ``M2.2`` (beta), and pickup-shaped leaf steps.

Shared by the milestone full-review tests (M11.13) and the unplanned-removal tests (M15.18).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from tests.helpers import DOGFOOD
from tests.review_repo_helpers import commit_file, git

from specy_road.bundled_scripts.roadmap_chunk_utils import load_json_chunk

KEYS = {"M2": "50000000-0000-4000-8000-000000000001", "M2.1": "50000000-0000-4000-8000-000000000002",
        "M2.2": "50000000-0000-4000-8000-000000000003"}
LEAVES = {"M2.1": "alpha", "M2.2": "beta"}


def milestone_node(nid: str, parent: str | None, kind: str, codename: str | None = None) -> dict:
    slug = codename or "unnamed"
    return {"id": nid, "node_key": KEYS[nid], "parent_id": parent, "type": kind, "title": f"Node {nid}",
            "planning_dir": f"planning/{nid}_{slug}_{KEYS[nid]}.md", "status": "Not Started",
            "touch_zones": ["src"], "dependencies": [], **({"codename": codename} if codename else {})}


def chunk_path(root: Path) -> Path:
    return root / "roadmap" / "phases" / "M2.json"


def set_status(root: Path, nid: str, status: str) -> None:
    nodes = load_json_chunk(chunk_path(root))
    next(n for n in nodes if n["id"] == nid)["status"] = status
    chunk_path(root).write_text(json.dumps({"nodes": nodes}, indent=2) + "\n", encoding="utf-8")


def branch_leaf(root: Path, nid: str) -> None:
    """Pickup-shaped branch for ``nid``: register, implement, complete; left checked out, not merged."""
    codename = LEAVES[nid]
    git(root, "checkout", "-q", "-b", f"feature/rm-{codename}", "dev")
    commit_file(root, "roadmap/registry.yaml", f"version: 1\nentries: []\n# {codename}\n",
                f"chore(rm-{codename}): register as in-progress")
    commit_file(root, f"src/{codename}.py", f"print({codename!r})\n", f"feat({codename}): implement")
    set_status(root, nid, "Complete")
    git(root, "add", "roadmap/phases/M2.json")
    git(root, "commit", "-qm", f"chore(rm-{codename}): complete, deregister")


def merge_leaf(root: Path, nid: str) -> None:
    git(root, "checkout", "-q", "dev")
    git(root, "merge", "-q", "--no-ff", "--no-edit", f"feature/rm-{LEAVES[nid]}")


def land_leaf(root: Path, nid: str) -> None:
    branch_leaf(root, nid)
    merge_leaf(root, nid)


def make_milestone_repo(tmp_path: Path, *, orchestration: str | None = None, land: bool = True) -> Path:
    """``dev`` with phase ``M2`` over leaves ``M2.1`` and ``M2.2``, both landed unless ``land`` is false."""
    root = tmp_path / "r"
    (root / "roadmap" / "phases").mkdir(parents=True)
    git(root, "init", "-q", "-b", "dev")
    git(root, "config", "user.email", "t@e.com")
    git(root, "config", "user.name", "T")
    shutil.copytree(DOGFOOD / "schemas", root / "schemas")
    nodes = [milestone_node("M2", None, "phase"), milestone_node("M2.1", "M2", "task", "alpha"),
             milestone_node("M2.2", "M2", "task", "beta")]
    (root / "roadmap" / "manifest.json").write_text(json.dumps({"version": 1, "includes": ["phases/M2.json"]}))
    chunk_path(root).write_text(json.dumps({"nodes": nodes}, indent=2) + "\n", encoding="utf-8")
    for n in nodes:
        sheet = root / n["planning_dir"]
        sheet.parent.mkdir(parents=True, exist_ok=True)
        sheet.write_text(f"# {n['id']}\n\n## Intent\n\nDo it.\n\n## References\n", encoding="utf-8")
    (root / "roadmap" / "git-workflow.yaml").write_text(
        "version: 1\nintegration_branch: dev\nremote: origin\nrequire_implementation_review_before_finish: true\n")
    (root / "roadmap" / "registry.yaml").write_text("version: 1\nentries: []\n")
    if orchestration is not None:
        (root / "roadmap" / "orchestration.yaml").write_text(orchestration)
    (root / ".gitignore").write_text("work/reviews/\n.specyrd/\n")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "graph")
    if land:
        for nid in LEAVES:
            land_leaf(root, nid)
    return root
