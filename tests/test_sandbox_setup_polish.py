"""Rough edges a sandbox setup run hit on a freshly scaffolded project."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests.helpers import REPO, script_subprocess_env


def _cli(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "specy_road.cli", *args, "--repo-root", str(root)],
        cwd=REPO,
        env=script_subprocess_env(),
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.fixture()
def two_new_phases(tmp_path: Path) -> Path:
    subprocess.run(
        [sys.executable, "-m", "specy_road.cli", "init", "project", str(tmp_path)],
        cwd=REPO, env=script_subprocess_env(), check=True, capture_output=True,
    )
    for nid, title in (("M2", "Alpha phase"), ("M3", "Beta phase")):
        _cli(tmp_path, "add-node", "--id", nid, "--type", "phase",
             "--parent-id", "null", "--title", title)
    return tmp_path


def test_new_phase_chunks_append_to_includes_in_creation_order(two_new_phases: Path) -> None:
    manifest = json.loads((two_new_phases / "roadmap" / "manifest.json").read_text())
    assert manifest["includes"] == ["phases/M1.json", "phases/M2.json", "phases/M3.json"]

