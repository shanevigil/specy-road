"""Pre-release file-safety regressions: shared brainstorm sessions."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import yaml

from tests.helpers import DOGFOOD, REPO, script_subprocess_env


def _brainstorm(repo: Path, *args: str) -> subprocess.Popen[str]:
    return subprocess.Popen(
        [sys.executable, "-m", "specy_road.cli", "brainstorm", *args, "--repo-root", str(repo)],
        cwd=REPO, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=script_subprocess_env(),
    )


def test_concurrent_add_idea_keeps_every_idea_with_distinct_ids(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    shutil.copytree(DOGFOOD, repo)
    assert _brainstorm(repo, "start", "--slug", "panel").wait() == 0

    shards = [_brainstorm(repo, "add-idea", "--slug", "panel", "--title", f"idea {n}") for n in range(8)]
    assert [p.wait() for p in shards] == [0] * 8, [p.stderr.read() for p in shards]

    ideas = yaml.safe_load((repo / "work" / "brainstorm-panel.yaml").read_text(encoding="utf-8"))["ideas"]
    assert sorted(i["title"] for i in ideas) == sorted(f"idea {n}" for n in range(8))
    assert len({i["id"] for i in ideas}) == 8
