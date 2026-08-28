"""``finish-this-task`` closes ancestors whose last leaf descendant just landed.

Regression cover for the v0.1.4-rc2 report: finish flipped only the leaf, so the
phase above it kept its authored ``Not Started`` forever. Readers computed the
rollup and showed Complete; the chunk on disk and ``list-nodes`` disagreed.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from roadmap_chunk_utils import load_json_chunk, write_json_chunk
from roadmap_load import annotate_rollup_status, load_roadmap
from specy_road.finish_ancestor_rollup import (
    complete_rolled_up_ancestors,
    rolled_up_stale_ancestor_ids,
)
from tests.helpers import REPO, SCHEMAS

NK = {
    "M60": "40000000-0000-4000-8000-000000000001",
    "M60.1": "40000000-0000-4000-8000-000000000002",
    "M60.1.1": "40000000-0000-4000-8000-000000000003",
}


def _nodes(leaf_status: str = "Complete") -> list[dict]:
    return [
        {
            "id": "M60",
            "node_key": NK["M60"],
            "parent_id": None,
            "type": "phase",
            "title": "Rollup phase",
            "planning_dir": f"planning/M60_unnamed_{NK['M60']}.md",
            "status": "Not Started",
            "touch_zones": [],
            "dependencies": [],
        },
        {
            "id": "M60.1",
            "node_key": NK["M60.1"],
            "parent_id": "M60",
            "type": "milestone",
            "title": "Rollup milestone",
            "planning_dir": f"planning/M60.1_unnamed_{NK['M60.1']}.md",
            "status": "Not Started",
            "touch_zones": [],
            "dependencies": [],
        },
        {
            "id": "M60.1.1",
            "node_key": NK["M60.1.1"],
            "parent_id": "M60.1",
            "type": "task",
            "title": "Rollup leaf",
            "codename": "rollup-leaf",
            "planning_dir": f"planning/M60.1.1_rollup-leaf_{NK['M60.1.1']}.md",
            "status": leaf_status,
            "touch_zones": [],
            "dependencies": [],
        },
    ]


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    shutil.copytree(SCHEMAS, tmp_path / "schemas")
    shutil.copytree(REPO / "constraints", tmp_path / "constraints")
    (tmp_path / "roadmap" / "phases").mkdir(parents=True)
    (tmp_path / "shared").mkdir()
    (tmp_path / "shared" / "README.md").write_text("# Shared\n", encoding="utf-8")
    (tmp_path / "roadmap" / "registry.yaml").write_text(
        "version: 1\nentries: []\n", encoding="utf-8"
    )
    (tmp_path / "roadmap" / "manifest.json").write_text(
        json.dumps({"version": 1, "includes": ["phases/T.json"]}) + "\n",
        encoding="utf-8",
    )
    planning = tmp_path / "planning"
    planning.mkdir()
    for node in _nodes():
        (planning / node["planning_dir"].split("/", 1)[1]).write_text(
            f"# {node['id']}\n", encoding="utf-8"
        )
    write_json_chunk(tmp_path / "roadmap" / "phases" / "T.json", _nodes())
    return tmp_path


def _own_statuses(root: Path) -> dict[str, str]:
    nodes = load_json_chunk(root / "roadmap" / "phases" / "T.json")
    return {n["id"]: n["status"] for n in nodes}


def test_identifies_stale_ancestors_nearest_first() -> None:
    assert rolled_up_stale_ancestor_ids(annotate_rollup_status(_nodes()), "M60.1.1") == [
        "M60.1",
        "M60",
    ]


def test_identifies_nothing_while_work_remains() -> None:
    nodes = annotate_rollup_status(_nodes(leaf_status="In Progress"))
    assert rolled_up_stale_ancestor_ids(nodes, "M60.1.1") == []


def test_skips_ancestors_owned_by_the_milestone_rollup_state_machine() -> None:
    """``reconcile-milestone-status`` closes those only once the rollup branch merges."""
    nodes = _nodes()
    next(n for n in nodes if n["id"] == "M60.1")["milestone_execution"] = {
        "state": "active",
        "rollup_branch": "rm/M60.1",
        "integration_branch": "main",
    }
    stale = rolled_up_stale_ancestor_ids(annotate_rollup_status(nodes), "M60.1.1")
    assert stale == ["M60"]


def test_completes_both_ancestors_and_reports_the_changed_chunk(repo: Path) -> None:
    changed = complete_rolled_up_ancestors(repo, "M60.1.1")
    assert changed == ["roadmap/phases/T.json"]
    assert _own_statuses(repo) == {
        "M60": "Complete",
        "M60.1": "Complete",
        "M60.1.1": "Complete",
    }
    # And the authored graph now agrees with what every reader computes.
    for node in load_roadmap(repo)["nodes"]:
        assert node["status"] == node["rollup_status"]


def test_is_a_no_op_when_the_leaf_is_not_finished(repo: Path) -> None:
    write_json_chunk(
        repo / "roadmap" / "phases" / "T.json", _nodes(leaf_status="In Progress")
    )
    assert complete_rolled_up_ancestors(repo, "M60.1.1") == []
    assert _own_statuses(repo)["M60"] == "Not Started"


def test_survives_a_repo_with_no_loadable_roadmap(tmp_path: Path) -> None:
    """Status hygiene must never fail a finish that already succeeded."""
    assert complete_rolled_up_ancestors(tmp_path, "M60.1.1") == []
