"""Tests for ``specy-road init project``."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from tests.helpers import BUNDLED_SCRIPTS, REPO, script_subprocess_env


def test_init_project_scaffold_validates(tmp_path: Path) -> None:
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "specy_road.cli",
            "init",
            "project",
            str(tmp_path),
        ],
        cwd=REPO,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "Initialized specy-road layout" in r.stdout
    where = tmp_path.resolve()
    block = [
        f"Next steps (run from {where}):",
        "  1. git init",
        "  2. Set integration_branch and remote in roadmap/git-workflow.yaml",
        '  3. git add -A && git commit -m "specy-road init"',
        "  4. specy-road validate",
    ]
    lines = r.stdout.splitlines()
    assert lines[-len(block):] == block
    assert lines[-len(block) - 1] == f"Initialized specy-road layout under {where}"
    assert (tmp_path / "roadmap" / "manifest.json").is_file()
    assert (tmp_path / "AGENTS.md").is_file()
    assert (tmp_path / "research" / "README.md").is_file()
    v = subprocess.run(
        [
            sys.executable,
            str(BUNDLED_SCRIPTS / "validate_roadmap.py"),
            "--repo-root",
            str(tmp_path),
        ],
        cwd=REPO,
        env=script_subprocess_env(),
        capture_output=True,
        text=True,
    )
    assert v.returncode == 0, v.stderr


def test_init_project_refuses_existing_manifest_without_force(tmp_path: Path) -> None:
    (tmp_path / "roadmap").mkdir(parents=True)
    (tmp_path / "roadmap" / "manifest.json").write_text('{"version": 1, "includes": []}\n')
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "specy_road.cli",
            "init",
            "project",
            str(tmp_path),
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 1
    assert "already exists" in (r.stderr or "")


def test_init_project_scaffold_passes_its_own_file_limits(tmp_path: Path) -> None:
    """A fresh scaffold must clear the caps its own ``constraints/file-limits.yaml`` sets (regressed in rc3)."""
    env = script_subprocess_env()
    subprocess.run([sys.executable, "-m", "specy_road.cli", "init", "project", str(tmp_path)],
                   cwd=REPO, env=env, check=True, capture_output=True, text=True)
    r = subprocess.run([sys.executable, "-m", "specy_road.cli", "file-limits", "--repo-root", str(tmp_path)],
                       cwd=REPO, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
