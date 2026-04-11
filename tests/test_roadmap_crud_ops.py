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


def test_parse_checklist_flags_partial_rejected() -> None:
    ns = SimpleNamespace(
        artifact_action="build x",
        contract_citation=None,
        interface_contract="i",
        constraints_note="c",
        dependency_note="d",
    )
    with pytest.raises(SystemExit):
        ops.parse_checklist_flags(ns)


def test_checklist_json_requires_all_fields() -> None:
    with pytest.raises(SystemExit):
        ops._checklist_from_json(json.dumps({"artifact_action": "a"}))


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
        execution_subtask=None,
        parallel_tracks=None,
        touch_zone=[],
        dependency=[],
        chunk="phases/T.json",
        checklist_json=None,
        artifact_action=None,
        contract_citation=None,
        interface_contract=None,
        constraints_note=None,
        dependency_note=None,
    )
    with pytest.raises(SystemExit):
        ops.cmd_add(args)


def test_cmd_add_direct_agentic_with_json_checklist(tmp_path: Path) -> None:
    _fixture_repo(tmp_path)
    args = SimpleNamespace(
        repo_root=tmp_path,
        id="M99.3",
        type="task",
        title="Three",
        parent_id="M99",
        codename="three",
        status="Not Started",
        execution_milestone=None,
        execution_subtask="agentic",
        parallel_tracks=None,
        touch_zone=[],
        dependency=[],
        chunk="phases/T.json",
        checklist_json=json.dumps(
            {
                "artifact_action": "a",
                "contract_citation": "shared/README.md",
                "interface_contract": "i",
                "constraints_note": "c",
                "dependency_note": "d",
            }
        ),
        artifact_action=None,
        contract_citation=None,
        interface_contract=None,
        constraints_note=None,
        dependency_note=None,
    )
    ops.cmd_add(args)
    nodes = load_json_chunk(tmp_path / "roadmap" / "phases" / "T.json")
    added = next(n for n in nodes if n["id"] == "M99.3")
    assert added["codename"] == "three"
