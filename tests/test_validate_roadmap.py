"""Tests for roadmap validation logic and script."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent

import validate_roadmap as vr


def test_cycle_check_detects_cycle() -> None:
    nodes = [
        {"id": "M1", "dependencies": ["M2"]},
        {"id": "M2", "dependencies": ["M1"]},
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
                "spec_citation": "x",
                "interface_contract": "x",
                "constraints_note": "x",
                "dependency_note": "x",
            },
        },
    ]
    with pytest.raises(SystemExit):
        vr.validate_agentic_checklists(nodes)


def test_validate_script_exits_zero_on_repo() -> None:
    subprocess.run(
        [sys.executable, str(REPO / "scripts" / "validate_roadmap.py")],
        cwd=REPO,
        check=True,
    )
