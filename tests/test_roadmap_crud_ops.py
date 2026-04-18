"""Focused unit tests for roadmap_crud_ops internals."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

import roadmap_crud_ops as ops
from roadmap_chunk_utils import load_json_chunk, write_json_chunk
from tests.helpers import REPO, SCHEMAS


def _sheet_stub(nid: str, _nk: str) -> str:
    return f"# {nid}\n"


def _m99_ops_nodes() -> tuple[str, str, str, list[dict]]:
    # Post F-003/F-007: every leaf is agentic by design; no per-node checklist.
    nk99 = "10000000-0000-4000-8000-000000009901"
    nk991 = "10000000-0000-4000-8000-000000009902"
    nk992 = "10000000-0000-4000-8000-000000009903"
    nodes: list[dict] = [
        {
            "id": "M99",
            "node_key": nk99,
            "parent_id": None,
            "type": "phase",
            "title": "P",
            "codename": None,
            "planning_dir": f"planning/M99_unnamed_{nk99}.md",
            "execution_milestone": "Human-led",
            "status": "Complete",
            "touch_zones": [],
            "dependencies": [],
            "parallel_tracks": 1,
        },
        {
            "id": "M99.1",
            "node_key": nk991,
            "parent_id": "M99",
            "type": "task",
            "title": "One",
            "codename": "one",
            "planning_dir": f"planning/M99.1_one_{nk991}.md",
            "execution_milestone": "Agentic-led",
            "status": "Not Started",
            "touch_zones": [],
            "dependencies": [],
            "parallel_tracks": 1,
        },
        {
            "id": "M99.2",
            "node_key": nk992,
            "parent_id": "M99",
            "type": "task",
            "title": "Two",
            "codename": "two",
            "planning_dir": f"planning/M99.2_two_{nk992}.md",
            "execution_milestone": "Agentic-led",
            "status": "Not Started",
            "touch_zones": [],
            "dependencies": [nk991],
            "parallel_tracks": 1,
        },
    ]
    return nk99, nk991, nk992, nodes


def _fixture_repo(dest: Path) -> None:
    """Minimal valid repo for CRUD ops tests (matches validator + git-workflow contract)."""
    shutil.copytree(SCHEMAS, dest / "schemas")
    shutil.copytree(REPO / "constraints", dest / "constraints")
    (dest / "roadmap" / "phases").mkdir(parents=True)
    (dest / "shared").mkdir(parents=True)
    (dest / "shared" / "README.md").write_text("# Shared\n", encoding="utf-8")
    (dest / "roadmap" / "git-workflow.yaml").write_text(
        "version: 1\nintegration_branch: main\nremote: origin\n",
        encoding="utf-8",
    )
    (dest / "roadmap" / "registry.yaml").write_text(
        "version: 1\nentries: []\n",
        encoding="utf-8",
    )
    (dest / "roadmap" / "manifest.json").write_text(
        json.dumps({"version": 1, "includes": ["phases/T.json"]}) + "\n",
        encoding="utf-8",
    )
    nk99, nk991, nk992, nodes = _m99_ops_nodes()
    pl = dest / "planning"
    pl.mkdir(parents=True)
    (pl / f"M99_unnamed_{nk99}.md").write_text(_sheet_stub("M99", nk99), encoding="utf-8")
    (pl / f"M99.1_one_{nk991}.md").write_text(_sheet_stub("M99.1", nk991), encoding="utf-8")
    (pl / f"M99.2_two_{nk992}.md").write_text(_sheet_stub("M99.2", nk992), encoding="utf-8")
    write_json_chunk(dest / "roadmap" / "phases" / "T.json", nodes)


def test_edit_node_set_pairs_updates_status_direct(tmp_path: Path) -> None:
    _fixture_repo(tmp_path)
    ops.edit_node_set_pairs(tmp_path, "M99.1", [("status", "Complete")])
    nodes = load_json_chunk(tmp_path / "roadmap" / "phases" / "T.json")
    node = next(n for n in nodes if n["id"] == "M99.1")
    assert node["status"] == "Complete"


def test_delete_roadmap_node_hard_dependency_guard(tmp_path: Path) -> None:
    _fixture_repo(tmp_path)
    with pytest.raises(ValueError, match="depends on node_key"):
        ops.delete_roadmap_node_hard(tmp_path, "M99.1")


def test_cmd_add_direct_rejects_invalid_codename(tmp_path: Path) -> None:
    _fixture_repo(tmp_path)
    args = SimpleNamespace(
        repo_root=tmp_path,
        id="M99.3",
        type="task",
        title="Three",
        parent_id="M99",
        codename="Not Kebab",
        status="Not Started",
        execution_milestone=None,
        parallel_tracks=None,
        touch_zone=[],
        dependency=[],
        chunk="phases/T.json",
    )
    with pytest.raises(SystemExit):
        ops.cmd_add(args)


def test_cmd_add_direct_auto_derives_codename(tmp_path: Path) -> None:
    """F-006: when --codename is not supplied on a task, derive from --title."""
    _fixture_repo(tmp_path)
    args = SimpleNamespace(
        repo_root=tmp_path,
        id="M99.3",
        type="task",
        title="Three Slug",
        parent_id="M99",
        codename=None,
        status="Not Started",
        execution_milestone=None,
        parallel_tracks=None,
        touch_zone=[],
        dependency=[],
        chunk="phases/T.json",
    )
    ops.cmd_add(args)
    nodes = load_json_chunk(tmp_path / "roadmap" / "phases" / "T.json")
    added = next(n for n in nodes if n["id"] == "M99.3")
    assert added["codename"] == "three-slug"
