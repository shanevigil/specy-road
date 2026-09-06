"""`specy-road move-node`: re-parent a subtree, renumber, and stay atomic.

`edit-node --set parent_id=` moves the edge and leaves the display id behind, so
re-parenting meant hand-editing two chunk files and renaming a planning sheet.
The move/renumber logic already existed for the PM GUI's outline drag; these
tests cover exposing it — including the part that was *not* already true, that
a rejected move leaves nothing behind.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from specy_road.bundled_scripts.roadmap_chunk_utils import write_json_chunk
from specy_road.bundled_scripts.roadmap_load import load_roadmap
from specy_road.bundled_scripts.roadmap_move_node import move_node
from tests.helpers import BUNDLED_SCRIPTS, REPO, SCHEMAS, script_subprocess_env

NK_A = "20000000-0000-4000-8000-00000000aa01"
NK_A1 = "20000000-0000-4000-8000-00000000aa02"
NK_B = "20000000-0000-4000-8000-00000000bb01"
NK_B1 = "20000000-0000-4000-8000-00000000bb02"


def _phase(nid: str, nk: str, order: int) -> dict:
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


def _task(nid: str, nk: str, parent: str, codename: str) -> dict:
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


def _fixture(dest: Path) -> None:
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
        _phase("M1", NK_A, 0),
        _task("M1.1", NK_A1, "M1", "alpha-work"),
        _phase("M2", NK_B, 1),
        _task("M2.1", NK_B1, "M2", "beta-work"),
    ]
    planning = dest / "planning"
    planning.mkdir(parents=True)
    for n in nodes:
        rel = Path(n["planning_dir"])
        (dest / rel).write_text(f"# {n['id']}\n", encoding="utf-8")
    write_json_chunk(dest / "roadmap" / "phases" / "T.json", nodes)


def _run(tmp: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(BUNDLED_SCRIPTS / "roadmap_move_node.py"), *args],
        cwd=tmp,
        capture_output=True,
        text=True,
        env=script_subprocess_env(),
    )


def _by_key(root: Path) -> dict[str, dict]:
    return {n["node_key"]: n for n in load_roadmap(root)["nodes"]}


def test_move_reparents_and_renumbers(tmp_path: Path) -> None:
    _fixture(tmp_path)

    r = _run(tmp_path, "--repo-root", str(tmp_path), "M1.1", "--to-parent", "M2")

    assert r.returncode == 0, r.stderr
    nodes = _by_key(tmp_path)
    assert nodes[NK_A1]["parent_id"] == nodes[NK_B]["id"]
    # The leaf left M1 and joined M2, so its id is now positional under M2.
    assert nodes[NK_A1]["id"].startswith(nodes[NK_B]["id"] + ".")


def test_the_old_to_new_id_map_is_printed(tmp_path: Path) -> None:
    """A move renumbers; changing ids silently is the surprise to avoid."""
    _fixture(tmp_path)

    r = _run(tmp_path, "--repo-root", str(tmp_path), "M1.1", "--to-parent", "M2")

    assert "Display ids changed" in r.stdout
    assert "M1.1 -> " in r.stdout


def test_the_planning_sheet_follows_the_node(tmp_path: Path) -> None:
    _fixture(tmp_path)
    old = tmp_path / "planning" / f"M1.1_alpha-work_{NK_A1}.md"
    assert old.is_file()

    assert _run(tmp_path, "--repo-root", str(tmp_path), "M1.1", "--to-parent", "M2").returncode == 0

    new_id = _by_key(tmp_path)[NK_A1]["id"]
    assert not old.exists()
    assert (tmp_path / "planning" / f"{new_id}_alpha-work_{NK_A1}.md").is_file()


def test_a_registry_claim_follows_the_new_id(tmp_path: Path) -> None:
    _fixture(tmp_path)

    assert _run(tmp_path, "--repo-root", str(tmp_path), "M1.1", "--to-parent", "M2").returncode == 0

    text = (tmp_path / "roadmap" / "registry.yaml").read_text(encoding="utf-8")
    assert f"node_id: {_by_key(tmp_path)[NK_A1]['id']}" in text
    assert "codename: alpha-work" in text


def test_moving_to_the_root_is_spelled_null(tmp_path: Path) -> None:
    _fixture(tmp_path)

    r = _run(tmp_path, "--repo-root", str(tmp_path), "M1.1", "--to-parent", "null")

    assert r.returncode == 0, r.stderr
    assert _by_key(tmp_path)[NK_A1]["parent_id"] is None


def test_an_unknown_parent_is_refused_before_anything_moves(tmp_path: Path) -> None:
    _fixture(tmp_path)
    before = (tmp_path / "roadmap" / "phases" / "T.json").read_bytes()

    r = _run(tmp_path, "--repo-root", str(tmp_path), "M1.1", "--to-parent", "M9")

    assert r.returncode == 1
    assert "not an existing node id" in r.stderr
    assert (tmp_path / "roadmap" / "phases" / "T.json").read_bytes() == before


def test_a_node_cannot_move_under_its_own_descendant(tmp_path: Path) -> None:
    _fixture(tmp_path)

    r = _run(tmp_path, "--repo-root", str(tmp_path), "M1", "--to-parent", "M1.1")

    assert r.returncode == 1
    assert "descendant" in r.stderr


def test_a_rejected_move_leaves_the_working_tree_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The defect this command could have inherited: persist, then validate."""
    _fixture(tmp_path)
    chunk = tmp_path / "roadmap" / "phases" / "T.json"
    sheet = tmp_path / "planning" / f"M1.1_alpha-work_{NK_A1}.md"
    registry = tmp_path / "roadmap" / "registry.yaml"
    before = (chunk.read_bytes(), sheet.read_bytes(), registry.read_bytes())

    def boom(_root: Path) -> None:
        raise ValueError("roadmap: synthetic validation failure")

    monkeypatch.setattr(
        "specy_road.bundled_scripts.roadmap_move_node.run_validate_raise", boom
    )
    with pytest.raises(ValueError, match="synthetic"):
        move_node(tmp_path, NK_A1, "M2", None)

    assert (chunk.read_bytes(), sheet.read_bytes(), registry.read_bytes()) == before
    assert sheet.is_file()
    assert not list((tmp_path / "planning").glob("M2.*_alpha-work_*.md"))
