"""Tests for rollup vs integration merge detection."""

from __future__ import annotations

import subprocess
from pathlib import Path

from specy_road.git_milestone_delivery import rollup_merged_into_integration


def _git(repo: Path, *args: str) -> None:
    subprocess.check_call(["git", *args], cwd=repo)


def _commit(repo: Path, message: str) -> None:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "--allow-empty", "-m", message)


def _repo_with_merged_feature(tmp_path: Path) -> Path:
    bare = tmp_path / "remote.git"
    subprocess.check_call(["git", "init", "--bare", "-q", str(bare)])
    repo = tmp_path / "work"
    subprocess.check_call(["git", "init", "-q", "-b", "master", str(repo)])
    _git(repo, "config", "user.email", "t@e.com")
    _git(repo, "config", "user.name", "T")
    _git(repo, "remote", "add", "origin", str(bare))
    _commit(repo, "init")
    _git(repo, "push", "-q", "-u", "origin", "master")
    _git(repo, "checkout", "-b", "feature/rm-mile")
    _commit(repo, "milestone work")
    _git(repo, "push", "-q", "-u", "origin", "feature/rm-mile")
    _git(repo, "checkout", "master")
    _git(repo, "merge", "-q", "--ff-only", "feature/rm-mile")
    _git(repo, "push", "-q", "origin", "master")
    return repo


def test_rollup_merged_true_after_ff_merge_and_push(tmp_path: Path) -> None:
    repo = _repo_with_merged_feature(tmp_path)
    assert (
        rollup_merged_into_integration(
            repo,
            remote="origin",
            rollup_branch="feature/rm-mile",
            integration_branch="master",
        )
        is True
    )


def test_rollup_merged_none_when_remote_ref_missing(tmp_path: Path) -> None:
    repo = tmp_path / "solo"
    repo.mkdir()
    subprocess.check_call(["git", "init", "-q", "-b", "master", str(repo)])
    _git(repo, "config", "user.email", "t@e.com")
    _git(repo, "config", "user.name", "T")
    _commit(repo, "solo")
    assert (
        rollup_merged_into_integration(
            repo,
            remote="origin",
            rollup_branch="feature/rm-x",
            integration_branch="master",
        )
        is None
    )
