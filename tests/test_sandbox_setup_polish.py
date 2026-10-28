"""Rough edges a sandbox setup run hit on a freshly scaffolded project."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests.helpers import REPO, script_subprocess_env


def _run(module: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", module, *args],
        cwd=REPO,
        env=script_subprocess_env(),
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.fixture()
def two_new_phases(tmp_path: Path) -> Path:
    _run("specy_road.cli", "init", "project", str(tmp_path))
    for nid, title in (("M2", "Alpha phase"), ("M3", "Beta phase")):
        _run("specy_road.cli", "add-node", "--id", nid, "--type", "phase", "--parent-id", "null",
             "--title", title, "--repo-root", str(tmp_path))
    return tmp_path


def test_new_phase_chunks_append_to_includes_in_creation_order(two_new_phases: Path) -> None:
    manifest = json.loads((two_new_phases / "roadmap" / "manifest.json").read_text())
    assert manifest["includes"] == ["phases/M1.json", "phases/M2.json", "phases/M3.json"]


def test_new_phase_planning_sheet_is_named_from_its_title(two_new_phases: Path) -> None:
    names = sorted(p.name for p in (two_new_phases / "planning").glob("M[23]_*.md"))
    assert [n.split("_")[:2] for n in names] == [["M2", "alpha-phase"], ["M3", "beta-phase"]]


def test_specyrd_init_notes_already_initialized_only_once_stubs_exist(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    _run("specy_road.cli", "init", "project", str(tmp_path))
    assert (tmp_path / ".specyrd" / "manifest.json").is_file()  # init project records the layout
    specyrd = ("specy_road.specyrd_cli", "init", str(tmp_path), "--ai", "cursor", "--role", "dev", "--no-prompt")
    assert "already initialized" not in _run(*specyrd).stderr
    assert "already initialized" in _run(*specyrd).stderr
