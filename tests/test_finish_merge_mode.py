"""F-012: --on-complete merge actually merges, errors clearly when it can't."""

from __future__ import annotations

import subprocess
from pathlib import Path

from specy_road.finish_land_integration import (
    _integration_branch_present,
    land_merge_feature_into_integration,
)


def _git(repo: Path, *args: str) -> None:
    subprocess.check_call(["git", *args], cwd=repo)


def _commit(repo: Path, message: str) -> None:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "--allow-empty", "-m", message)


def _bootstrap(tmp_path: Path) -> tuple[Path, Path]:
    """Init a sandbox repo with a bare 'origin', and master + feature branches."""
    bare = tmp_path / "remote.git"
    subprocess.check_call(["git", "init", "--bare", "-q", str(bare)])
    repo = tmp_path / "work"
    subprocess.check_call(["git", "init", "-q", "-b", "master", str(repo)])
    _git(repo, "config", "user.email", "t@e.com")
    _git(repo, "config", "user.name", "T")
    _git(repo, "remote", "add", "origin", str(bare))
    _commit(repo, "init")
    _git(repo, "push", "-q", "-u", "origin", "master")
    _git(repo, "checkout", "-b", "feature/rm-x")
    _commit(repo, "feature work")
    _git(repo, "push", "-q", "-u", "origin", "feature/rm-x")
    return repo, bare


def test_land_merge_succeeds_when_integration_branch_is_master(tmp_path: Path) -> None:
    repo, _bare = _bootstrap(tmp_path)
    ok, err = land_merge_feature_into_integration(
        repo,
        remote="origin",
        integration_branch="master",
        feature_branch="feature/rm-x",
    )
    assert ok, err


def test_land_merge_returns_clear_error_when_integration_branch_missing(
    tmp_path: Path,
) -> None:
    """F-012: misconfigured integration_branch should fail loudly, not silently fall through."""
    repo, _bare = _bootstrap(tmp_path)
    # Real branch is master; misconfigure as 'main' which doesn't exist.
    ok, err = land_merge_feature_into_integration(
        repo,
        remote="origin",
        integration_branch="main",
        feature_branch="feature/rm-x",
    )
    assert ok is False
    assert "integration branch 'main' does not exist" in err
    assert "roadmap/git-workflow.yaml" in err


def test_integration_branch_present_finds_local_branch(tmp_path: Path) -> None:
    repo, _bare = _bootstrap(tmp_path)
    ok, where = _integration_branch_present(repo, "origin", "master")
    assert ok
    assert where == "refs/heads/master"
    ok2, _ = _integration_branch_present(repo, "origin", "main")
    assert ok2 is False
