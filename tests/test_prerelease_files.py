"""Pre-release file-safety regressions: shared brainstorm sessions."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest
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


def _cli(repo: Path, *args: str, module: str = "specy_road.cli") -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-m", module, *args], cwd=repo, capture_output=True, text=True,
                          env=script_subprocess_env())


def _snapshot(d: Path) -> dict[str, bytes]:
    return {str(p.relative_to(d)): p.read_bytes() for p in sorted(d.rglob("*")) if p.is_file()}


@pytest.mark.parametrize(("link", "outside_kind", "command"), [
    ("AGENTS.md", "file", "init"),
    ("AGENTS.md", "dangling", "init"),
    (".agents/skills", "dir", "refresh"),
    (".agents/skills/specyrd-validate/SKILL.md", "file", "refresh"),
    (".claude/skills", "dir", "refresh"),
    (".agents/skills/specyrd-validate/SKILL.md", "file", "specyrd"),
    (".claude/skills", "dir", "specyrd"),
])
def test_managed_writes_refuse_a_symlink_out_of_the_repo(tmp_path: Path, link: str, outside_kind: str,
                                                         command: str) -> None:
    repo, outside = tmp_path / "repo", tmp_path / "outside"
    repo.mkdir()
    outside.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    specyrd = ("init", ".", "--ai", "claude-code")
    if command != "init":
        assert _cli(repo, "init", "project", ".").returncode == 0
        assert _cli(repo, *specyrd, module="specy_road.specyrd_cli").returncode == 0
    target = outside / "target"
    if outside_kind == "file":
        target.write_text("SENTINEL\n", encoding="utf-8")
    elif outside_kind == "dir":
        (target / "specyrd-validate").mkdir(parents=True)
        (target / "specyrd-validate" / "SKILL.md").write_text("SENTINEL\n", encoding="utf-8")
    dest = repo / link
    if dest.is_dir() and not dest.is_symlink():
        shutil.rmtree(dest)
    dest.unlink(missing_ok=True)
    dest.symlink_to(target, target_is_directory=outside_kind == "dir")
    before = _snapshot(outside)

    r = {"init": lambda: _cli(repo, "init", "project", "."),
         "refresh": lambda: _cli(repo, "refresh-stubs"),
         "specyrd": lambda: _cli(repo, *specyrd, "--force", module="specy_road.specyrd_cli")}[command]()

    assert r.returncode == 0, r.stderr
    assert "refused: a symlink leads outside the repository" in r.stdout
    assert _snapshot(outside) == before
    assert not any(p.is_symlink() for p in outside.rglob("*"))
