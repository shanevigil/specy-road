"""Tests for roadmap CRUD and chunk utilities."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from roadmap_chunk_utils import find_chunk_path, write_json_chunk
from roadmap_crud_ops import append_node_to_chunk
from tests.helpers import BUNDLED_SCRIPTS, REPO, SCHEMAS, script_subprocess_env


def _fixture_repo(dest: Path) -> None:
    shutil.copytree(SCHEMAS, dest / "schemas")
    shutil.copytree(REPO / "constraints", dest / "constraints")
    (dest / "roadmap" / "phases").mkdir(parents=True)
    (dest / "shared").mkdir(parents=True)
    (dest / "shared" / "README.md").write_text("# Shared\n", encoding="utf-8")
    (dest / "roadmap" / "registry.yaml").write_text(
        "version: 1\nentries: []\n",
        encoding="utf-8",
    )
    (dest / "roadmap" / "manifest.json").write_text(
        json.dumps({"version": 1, "includes": ["phases/T.json"]}) + "\n",
        encoding="utf-8",
    )
    nk99 = "10000000-0000-4000-8000-000000009901"
    nk991 = "10000000-0000-4000-8000-000000009902"
    nk992 = "10000000-0000-4000-8000-000000009903"
    nodes = [
        {
            "id": "M99",
            "node_key": nk99,
            "parent_id": None,
            "type": "phase",
            "title": "P",
            "codename": None,
            "planning_dir": "planning/M99",
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
            "execution_milestone": "Agentic-led",
            "execution_subtask": "agentic",
            "agentic_checklist": {
                "artifact_action": "a",
                "contract_citation": "shared/README.md",
                "interface_contract": "i",
                "constraints_note": "c",
                "dependency_note": "d",
            },
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
            "execution_milestone": "Agentic-led",
            "execution_subtask": "agentic",
            "agentic_checklist": {
                "artifact_action": "a",
                "contract_citation": "shared/README.md",
                "interface_contract": "i",
                "constraints_note": "c",
                "dependency_note": "d",
            },
            "status": "Not Started",
            "touch_zones": [],
            "dependencies": [nk991],
            "parallel_tracks": 1,
        },
    ]
    pd = dest / "planning" / "M99"
    pd.mkdir(parents=True)
    (pd / "overview.md").write_text("# Overview\n", encoding="utf-8")
    (pd / "plan.md").write_text("# Plan\n", encoding="utf-8")
    write_json_chunk(dest / "roadmap" / "phases" / "T.json", nodes)


def _run_crud(tmp: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(BUNDLED_SCRIPTS / "roadmap_crud.py"), *args],
        cwd=tmp,
        capture_output=True,
        text=True,
        env=script_subprocess_env(),
    )


def test_find_chunk_path(tmp_path: Path) -> None:
    _fixture_repo(tmp_path)
    assert find_chunk_path(tmp_path, "M99.1") == tmp_path / "roadmap" / "phases" / "T.json"


def test_append_node_validate(tmp_path: Path) -> None:
    _fixture_repo(tmp_path)
    node = {
        "id": "M99.3",
        "node_key": "10000000-0000-4000-8000-000000009904",
        "parent_id": "M99",
        "type": "task",
        "title": "Three",
        "codename": "three",
        "execution_milestone": "Agentic-led",
        "execution_subtask": "agentic",
        "agentic_checklist": {
            "artifact_action": "x",
            "contract_citation": "shared/README.md",
            "interface_contract": "x",
            "constraints_note": "x",
            "dependency_note": "x",
        },
        "status": "Not Started",
        "touch_zones": [],
        "dependencies": [],
        "parallel_tracks": 1,
    }
    append_node_to_chunk(tmp_path, "phases/T.json", node)
    v = subprocess.run(
        [
            sys.executable,
            str(BUNDLED_SCRIPTS / "validate_roadmap.py"),
            "--repo-root",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        env=script_subprocess_env(),
    )
    assert v.returncode == 0, v.stderr


def test_hard_remove_blocked_by_dependency(tmp_path: Path) -> None:
    _fixture_repo(tmp_path)
    r = _run_crud(
        tmp_path,
        "--repo-root",
        str(tmp_path),
        "archive-node",
        "M99.1",
        "--hard-remove",
    )
    assert r.returncode == 1
    assert "depends" in r.stderr


def test_edit_node_cli(tmp_path: Path) -> None:
    _fixture_repo(tmp_path)
    r = _run_crud(
        tmp_path,
        "--repo-root",
        str(tmp_path),
        "edit-node",
        "M99.1",
        "--set",
        "status=Complete",
    )
    assert r.returncode == 0, r.stderr


def test_list_nodes_cli(tmp_path: Path) -> None:
    _fixture_repo(tmp_path)
    r = _run_crud(tmp_path, "--repo-root", str(tmp_path), "list-nodes")
    assert r.returncode == 0
    assert "M99.1" in r.stdout
