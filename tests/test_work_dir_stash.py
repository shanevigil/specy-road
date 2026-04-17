"""F-011: stash/restore work/ around the integration-branch registry commit."""

from __future__ import annotations

import subprocess
from pathlib import Path

from work_dir_stash import (
    restore_work_dir_changes,
    stash_work_dir_changes,
)


def _git(repo: Path, *args: str) -> None:
    subprocess.check_call(["git", *args], cwd=repo)


def _init_repo(tmp: Path) -> Path:
    repo = tmp / "r"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@e.com")
    _git(repo, "config", "user.name", "T")
    (repo / "README.md").write_text("# r\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-q", "-m", "init")
    return repo


def test_stash_returns_false_when_no_work_changes(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    assert stash_work_dir_changes(repo, "test") is False


def test_stash_returns_false_outside_a_git_repo(tmp_path: Path) -> None:
    # Plain dir, no .git.
    plain = tmp_path / "plain"
    plain.mkdir()
    assert stash_work_dir_changes(plain, "test") is False


def test_stash_then_restore_round_trips_an_untracked_file(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    work = repo / "work"
    work.mkdir()
    sentinel = work / "brief-M1.1.md"
    sentinel.write_text("hello\n", encoding="utf-8")
    # Stash work/ (sentinel is untracked).
    assert stash_work_dir_changes(repo, "test") is True
    # After stash, the sentinel is gone from the working tree.
    assert not sentinel.is_file()
    # Now restore.
    restore_work_dir_changes(repo, True)
    assert sentinel.is_file()
    assert sentinel.read_text(encoding="utf-8") == "hello\n"


def test_restore_is_no_op_when_nothing_was_stashed(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    # Should not raise even with no stashes.
    restore_work_dir_changes(repo, False)
