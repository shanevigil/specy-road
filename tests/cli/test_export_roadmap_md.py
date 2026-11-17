"""Tests for markdown export."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from tests.helpers import BUNDLED_SCRIPTS, DOGFOOD, REPO, script_subprocess_env


def test_export_check_matches_repo() -> None:
    script = str(BUNDLED_SCRIPTS / "export_roadmap_md.py")
    subprocess.run(
        [
            sys.executable,
            script,
            "--check",
            "--repo-root",
            str(DOGFOOD),
        ],
        cwd=REPO,
        env=script_subprocess_env(),
        check=True,
    )


def test_export_check_names_how_to_fix_drift(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    shutil.copytree(DOGFOOD, root)
    roadmap = root / "roadmap.md"
    roadmap.write_text(roadmap.read_text(encoding="utf-8") + "\nstale\n", encoding="utf-8")

    proc = subprocess.run(
        [
            sys.executable,
            str(BUNDLED_SCRIPTS / "export_roadmap_md.py"),
            "--check",
            "--repo-root",
            str(root),
        ],
        cwd=REPO,
        env=script_subprocess_env(),
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 1
    assert proc.stderr.splitlines()[0] == (
        f"drift: {roadmap.resolve()} no longer matches the roadmap. Run: specy-road export"
    )
