"""Tests for markdown export."""

from __future__ import annotations

import shutil
from pathlib import Path

from tests.helpers import DOGFOOD, REPO, script_subprocess_env
from tests.support.cli import run_script


def test_export_check_matches_repo() -> None:
    argv = ["--check", "--repo-root", str(DOGFOOD)]
    result = run_script("export_roadmap_md.py", argv, cwd=REPO, env=script_subprocess_env())
    result.check_returncode()


def test_export_check_names_how_to_fix_drift(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    shutil.copytree(DOGFOOD, root)
    roadmap = root / "roadmap.md"
    roadmap.write_text(roadmap.read_text(encoding="utf-8") + "\nstale\n", encoding="utf-8")

    proc = run_script(
        "export_roadmap_md.py",
        ["--check", "--repo-root", str(root)],
        cwd=REPO,
        env=script_subprocess_env(),
    )

    assert proc.returncode == 1
    assert proc.stderr.splitlines()[0] == (
        f"drift: {roadmap.resolve()} no longer matches the roadmap. Run: specy-road export"
    )
