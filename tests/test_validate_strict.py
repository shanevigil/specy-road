"""`validate --strict`: a passing validation that warned exits 1 (rc1 feedback: CI after an upgrade)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from specy_road.init_project import run_init_project
from tests.helpers import REPO, script_subprocess_env


def _validate(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "specy_road.cli", "validate", "--repo-root", str(root), *args],
        cwd=REPO, env=script_subprocess_env(), capture_output=True, text=True,
    )


def _scaffold(root: Path, *, acceptance: bool) -> Path:
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    assert run_init_project(root) == 0
    if acceptance:
        r = subprocess.run(
            [sys.executable, "-m", "specy_road.cli", "edit-node", "M1.1", "--repo-root", str(root),
             "--set", "acceptance=Works"],
            cwd=REPO, env=script_subprocess_env(), capture_output=True, text=True,
        )
        assert r.returncode == 0, r.stderr
    return root


def test_strict_fails_a_validation_that_warned(tmp_path: Path) -> None:
    root = _scaffold(tmp_path, acceptance=False)

    assert _validate(root).returncode == 0
    r = _validate(root, "--strict")

    assert r.returncode == 1
    assert "has no acceptance criteria" in r.stderr
    assert "FAILED (--strict)" in r.stderr
    assert "OK: roadmap and registry validate." in r.stdout


def test_strict_passes_a_quiet_validation(tmp_path: Path) -> None:
    root = _scaffold(tmp_path, acceptance=True)

    r = _validate(root, "--strict")

    assert r.returncode == 0, r.stderr
    assert r.stderr == ""
