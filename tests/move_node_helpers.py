"""Shared fixture and runner for the `specy-road move-node` tests.

Two root phases with one leaf each is the smallest graph a move can change;
``wide_fixture`` adds a nested milestone and gaps for the subtree-only default.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from specy_road.bundled_scripts.roadmap_chunk_utils import (
    load_json_chunk,
    write_json_chunk,
)
from specy_road.bundled_scripts.roadmap_load import load_roadmap
from tests.helpers import BUNDLED_SCRIPTS, REPO, SCHEMAS, script_subprocess_env

NK_A = "20000000-0000-4000-8000-00000000aa01"
NK_A1 = "20000000-0000-4000-8000-00000000aa02"
NK_B = "20000000-0000-4000-8000-00000000bb01"
NK_B1 = "20000000-0000-4000-8000-00000000bb02"


def phase_node(nid: str, nk: str, order: int) -> dict:
    return {
        "id": nid,
        "node_key": nk,
        "parent_id": None,
        "type": "phase",
        "title": f"Phase {nid}",
        "codename": None,
        "planning_dir": f"planning/{nid}_unnamed_{nk}.md",
        "execution_milestone": "Human-led",
        "status": "Not Started",
        "sibling_order": order,
        "touch_zones": [],
        "dependencies": [],
        "parallel_tracks": 1,
    }


def task_node(nid: str, nk: str, parent: str, codename: str) -> dict:
    return {
        "id": nid,
        "node_key": nk,
        "parent_id": parent,
        "type": "task",
        "title": codename.replace("-", " ").title(),
        "codename": codename,
        "planning_dir": f"planning/{nid}_{codename}_{nk}.md",
        "execution_milestone": "Agentic-led",
        "status": "Not Started",
        "sibling_order": 0,
        "touch_zones": [],
        "dependencies": [],
        "parallel_tracks": 1,
    }


def base_fixture(dest: Path) -> None:
    """Two root phases, one leaf each — the smallest graph a move can change."""
    shutil.copytree(SCHEMAS, dest / "schemas")
    shutil.copytree(REPO / "constraints", dest / "constraints")
    (dest / "roadmap" / "phases").mkdir(parents=True)
    (dest / "shared").mkdir(parents=True)
    (dest / "shared" / "README.md").write_text("# Shared\n", encoding="utf-8")
    (dest / "roadmap" / "registry.yaml").write_text(
        "version: 1\nentries:\n  - codename: alpha-work\n    node_id: M1.1\n"
        "    branch: feature/rm-alpha-work\n",
        encoding="utf-8",
    )
    (dest / "roadmap" / "manifest.json").write_text(
        json.dumps({"version": 1, "includes": ["phases/T.json"]}) + "\n",
        encoding="utf-8",
    )
    nodes = [
        phase_node("M1", NK_A, 0),
        task_node("M1.1", NK_A1, "M1", "alpha-work"),
        phase_node("M2", NK_B, 1),
        task_node("M2.1", NK_B1, "M2", "beta-work"),
    ]
    planning = dest / "planning"
    planning.mkdir(parents=True)
    for n in nodes:
        rel = Path(n["planning_dir"])
        (dest / rel).write_text(f"# {n['id']}\n", encoding="utf-8")
    write_json_chunk(dest / "roadmap" / "phases" / "T.json", nodes)


def run_move_node(tmp: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(BUNDLED_SCRIPTS / "roadmap_move_node.py"), *args],
        cwd=tmp,
        capture_output=True,
        text=True,
        env=script_subprocess_env(),
    )


def git(top: Path, *args: str) -> None:
    """Run ``git`` in ``top`` with a throwaway identity; raise on failure."""
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=top, check=True, capture_output=True,
    )


def run_cli(tmp: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run a `specy-road` command through the real dispatcher, on ``tmp``."""
    return subprocess.run(
        [sys.executable, "-m", "specy_road.cli", *args, "--repo-root", str(tmp)],
        cwd=tmp,
        capture_output=True,
        text=True,
        env=script_subprocess_env(),
    )


def nodes_by_key(root: Path) -> dict[str, dict]:
    return {n["node_key"]: n for n in load_roadmap(root)["nodes"]}


def set_zones(root: Path, zones_by_id: dict[str, list[str]]) -> None:
    chunk = root / "roadmap" / "phases" / "T.json"
    nodes = load_json_chunk(chunk)
    for n in nodes:
        n["touch_zones"] = zones_by_id.get(n["id"], n["touch_zones"])
    write_json_chunk(chunk, nodes)


def lock_milestone(root: Path, node_key: str) -> None:
    """Put the node's subtree under an active milestone execution."""
    chunk = root / "roadmap" / "phases" / "T.json"
    nodes = load_json_chunk(chunk)
    for n in nodes:
        if n["node_key"] == node_key:
            n["milestone_execution"] = {"state": "active"}
    write_json_chunk(chunk, nodes)


# A wider graph for the subtree-only default: M1 holds a leaf, a milestone
# M1.2 with three leaves and a gap (M1.2.1, M1.2.2, M1.2.4), and another leaf;
# M2 has a gap before M2.4.
NK_A2 = "20000000-0000-4000-8000-00000000aa03"
NK_A21 = "20000000-0000-4000-8000-00000000aa04"
NK_A22 = "20000000-0000-4000-8000-00000000aa05"
NK_A24 = "20000000-0000-4000-8000-00000000aa06"
NK_A3 = "20000000-0000-4000-8000-00000000aa07"
NK_B4 = "20000000-0000-4000-8000-00000000bb03"


def wide_fixture(dest: Path) -> None:
    base_fixture(dest)
    middle = task_node("M1.2", NK_A2, "M1", "middle-work")
    middle.update(type="milestone", codename=None, execution_milestone="Mixed")
    middle["planning_dir"] = f"planning/M1.2_unnamed_{NK_A2}.md"
    extra = [
        middle,
        task_node("M1.2.1", NK_A21, "M1.2", "inner-one"),
        task_node("M1.2.2", NK_A22, "M1.2", "inner-two"),
        task_node("M1.2.4", NK_A24, "M1.2", "inner-four"),
        task_node("M1.3", NK_A3, "M1", "last-work"),
        task_node("M2.4", NK_B4, "M2", "gap-work"),
    ]
    for n, order in zip(extra, (1, 0, 1, 2, 2, 1)):
        n["sibling_order"] = order
    chunk = dest / "roadmap" / "phases" / "T.json"
    write_json_chunk(chunk, load_json_chunk(chunk) + extra)
    for n in extra:
        (dest / n["planning_dir"]).write_text(f"# {n['id']}\n", encoding="utf-8")
    registry = dest / "roadmap" / "registry.yaml"
    registry.write_text(
        registry.read_text(encoding="utf-8")
        + "  - codename: inner-two\n    node_id: M1.2.2\n"
        "    branch: feature/rm-inner-two\n"
        "  - codename: inner-four\n    node_id: M1.2.4\n"
        "    branch: feature/rm-inner-four\n",
        encoding="utf-8",
    )


def tree_bytes(root: Path) -> dict[str, bytes]:
    """Every file a roadmap write can touch, by path."""
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for folder in ("roadmap", "planning")
        for p in (root / folder).rglob("*")
        if p.is_file()
    }


def ids_by_key(root: Path) -> dict[str, str]:
    return {k: n["id"] for k, n in nodes_by_key(root).items()}


def sheet_names(root: Path) -> set[str]:
    return {p.name for p in (root / "planning").glob("*.md")}


def unchanged_except(before: dict[str, str], after: dict[str, str], keys: set[str]) -> bool:
    return {k: v for k, v in after.items() if k not in keys} == {
        k: v for k, v in before.items() if k not in keys
    }
