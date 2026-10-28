"""Defects from the 0.3.1-rc1 three-app user test (all present since 0.2.3)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from tests.helpers import REPO, script_subprocess_env


def _cli(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "specy_road.cli", *args, "--repo-root", str(root)],
        cwd=REPO,
        env=script_subprocess_env(),
        capture_output=True,
        text=True,
    )


def _scaffold(root: Path) -> None:
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    r = subprocess.run(
        [sys.executable, "-m", "specy_road.cli", "init", "project", str(root)],
        cwd=REPO,
        env=script_subprocess_env(),
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr


def test_move_node_keeps_the_scaffold_m1_numbering(tmp_path: Path) -> None:
    """The scaffold starts at M1; a move used to renumber every root to M0."""
    _scaffold(tmp_path)
    add = ("add-node", "--id", "M1.2", "--type", "task", "--title", "Second")
    assert _cli(tmp_path, *add, "--parent-id", "M1").returncode == 0

    r = _cli(tmp_path, "move-node", "M1.2", "--to-parent", "M1", "--index", "0")

    assert r.returncode == 0, r.stderr
    assert "[ok] moved M1.1 under M1" in r.stdout
    sheets = sorted(p.name.split("_")[0] for p in (tmp_path / "planning").glob("M*.md"))
    assert sheets == ["M1", "M1.1", "M1.2"]
