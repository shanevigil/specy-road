"""Tests for roadmap validation logic and script."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from tests.helpers import BUNDLED_SCRIPTS, DOGFOOD, REPO, script_subprocess_env

import validate_roadmap as vr


def test_cycle_check_detects_cycle() -> None:
    k1 = "10000000-0000-4000-8000-000000000001"
    k2 = "20000000-0000-4000-8000-000000000002"
    nodes = [
        {"id": "M1", "node_key": k1, "dependencies": [k2]},
        {"id": "M2", "node_key": k2, "dependencies": [k1]},
    ]
    with pytest.raises(SystemExit):
        vr.cycle_check(nodes)


def test_validate_codenames_duplicate() -> None:
    nodes = [
        {"id": "M1", "codename": "foo"},
        {"id": "M2", "codename": "foo"},
    ]
    with pytest.raises(SystemExit):
        vr.validate_codenames(nodes)


def test_validate_required_planning_dirs_phase() -> None:
    nodes = [
        {
            "id": "M1",
            "node_key": "10000000-0000-4000-8000-000000000001",
            "type": "phase",
        },
    ]
    with pytest.raises(SystemExit):
        vr.validate_required_planning_dirs(nodes)


def test_validate_required_planning_dirs_ok_when_set() -> None:
    nodes = [
        {
            "id": "M1",
            "node_key": "10000000-0000-4000-8000-000000000001",
            "type": "phase",
            "planning_dir": "planning/M1",
        },
    ]
    vr.validate_required_planning_dirs(nodes)


def test_validate_agentic_requires_checklist() -> None:
    nodes = [
        {
            "id": "M0.1.1",
            "execution_subtask": "agentic",
        },
    ]
    with pytest.raises(SystemExit):
        vr.validate_agentic_checklists(nodes)


def test_validate_agentic_rejects_checklist_when_not_agentic() -> None:
    nodes = [
        {
            "id": "M1",
            "execution_subtask": None,
            "agentic_checklist": {
                "artifact_action": "x",
                "contract_citation": "x",
                "interface_contract": "x",
                "constraints_note": "x",
                "dependency_note": "x",
            },
        },
    ]
    with pytest.raises(SystemExit):
        vr.validate_agentic_checklists(nodes)


def test_validate_contract_citations_warns_on_unknown_prefix(capsys) -> None:
    nodes = [
        {
            "id": "M1.1.1",
            "execution_subtask": "agentic",
            "agentic_checklist": {
                "artifact_action": "x",
                "contract_citation": "internal note without path",
                "interface_contract": "x",
                "constraints_note": "x",
                "dependency_note": "x",
            },
        },
    ]
    vr.validate_contract_citations(nodes)
    captured = capsys.readouterr()
    assert "warning" in captured.err
    assert "M1.1.1" in captured.err
    assert "contract_citation" in captured.err


def test_validate_contract_citations_silent_on_known_prefix(capsys) -> None:
    known = ("shared/api.md", "docs/adr/ADR-001.md", "specs/x.md", "adr/y.md")
    for prefix in known:
        nodes = [
            {
                "id": "M1.1.1",
                "execution_subtask": "agentic",
                "agentic_checklist": {
                    "artifact_action": "x",
                    "contract_citation": prefix,
                    "interface_contract": "x",
                    "constraints_note": "x",
                    "dependency_note": "x",
                },
            },
        ]
        vr.validate_contract_citations(nodes)
        captured = capsys.readouterr()
        assert "warning" not in captured.err, (
            f"unexpected warning for prefix {prefix}"
        )


def test_validate_script_exits_zero_on_repo() -> None:
    subprocess.run(
        [
            sys.executable,
            str(BUNDLED_SCRIPTS / "validate_roadmap.py"),
            "--repo-root",
            str(DOGFOOD),
        ],
        cwd=REPO,
        env=script_subprocess_env(),
        check=True,
    )
