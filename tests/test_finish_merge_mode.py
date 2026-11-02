"""F-012: --on-complete merge actually merges, errors clearly when it can't."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from specy_road.bundled_scripts import finish_task
from specy_road.finish_land_integration import (
    _integration_branch_present,
    land_merge_feature_into_integration,
    merge_push_disclosure_counts,
    print_merge_push_notice,
)
from tests.helpers import REPO
from tests.review_repo_helpers import commit_file, git, make_review_repo

BR = "feature/rm-x"


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


def _merge_mode_finish_repo(tmp_path: Path, monkeypatch) -> tuple[Path, Path]:
    monkeypatch.setenv("PYTHONPATH", str(REPO))
    repo = make_review_repo(tmp_path)
    git(repo, "checkout", "-q", "dev")
    commit_file(
        repo,
        "roadmap/git-workflow.yaml",
        "version: 1\nintegration_branch: dev\nremote: origin\non_complete: merge\n",
        "merge mode",
    )
    commit_file(repo, ".gitignore", "work/reviews/\n.specyrd/cache/\n", "gitignore")
    git(repo, "checkout", "-q", "feature/rm-thing")
    git(repo, "merge", "-q", "--no-edit", "dev")
    bare = tmp_path / "remote.git"
    git(tmp_path, "clone", "-q", "--bare", str(repo), str(bare))
    git(bare, "symbolic-ref", "HEAD", "refs/heads/dev")
    git(repo, "remote", "add", "origin", str(bare))
    git(repo, "fetch", "-q", "origin")
    return repo, bare


def _finish(repo: Path) -> int:
    with pytest.raises(SystemExit) as e:
        finish_task.main(["--repo-root", str(repo)])
        raise SystemExit(0)
    return e.value.code or 0


def test_merge_push_disclosure_counts_when_local_integration_branch_is_absent(
    tmp_path: Path, capsys,
) -> None:
    """A1: still disclose when ``refs/heads/<integration>`` is missing (tracking ref after fetch)."""
    repo, _bare = _bootstrap(tmp_path)
    _git(repo, "checkout", "-q", "master")
    tip = subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True,
    ).strip()
    _git(repo, "update-ref", "-d", "refs/heads/master")
    _git(repo, "update-ref", "-d", "refs/remotes/origin/master")
    print_merge_push_notice(
        repo, remote="origin", integration_branch="master", feature_branch=BR,
    )
    out = capsys.readouterr().out
    assert "The push will carry 1 commit (0 not from 'feature/rm-x')." in out
    _git(repo, "update-ref", "refs/remotes/origin/master", tip)
    _git(repo, "update-ref", "refs/heads/master", tip)
    total, not_from = merge_push_disclosure_counts(
        repo, remote="origin", integration_branch="master", feature_branch=BR,
    )
    assert (total, not_from) == (1, 0)


def test_merge_push_disclosure_counts_when_tracking_ref_is_absent(
    tmp_path: Path, capsys,
) -> None:
    """A1: still disclose when ``refs/remotes/<remote>/<integration>`` is absent."""
    repo, _bare = _bootstrap(tmp_path)
    _git(repo, "checkout", "-q", "master")
    _git(repo, "commit", "--allow-empty", "-qm", "only local integration")
    _git(repo, "remote", "remove", "origin")
    _git(repo, "update-ref", "-d", "refs/remotes/origin/master")
    print_merge_push_notice(
        repo, remote="origin", integration_branch="master", feature_branch=BR,
    )
    out = capsys.readouterr().out
    assert "The push will carry 2 commits (1 not from 'feature/rm-x')." in out


def test_finish_merge_prints_push_disclosure_for_unrelated_dev_commit(
    tmp_path: Path, monkeypatch, capsys,
) -> None:
    repo, _bare = _merge_mode_finish_repo(tmp_path, monkeypatch)
    git(repo, "checkout", "-q", "dev")
    base = git(repo, "rev-parse", "HEAD")
    git(repo, "commit", "--allow-empty", "-qm", "unrelated on dev")
    git(repo, "update-ref", "refs/remotes/origin/dev", base)
    git(repo, "checkout", "-q", "feature/rm-thing")
    assert _finish(repo) == 0
    out = capsys.readouterr().out
    assert "The push will carry 2 commits (1 not from 'feature/rm-thing')." in out
    assert "[ok] merged feature/rm-thing into dev and pushed to origin" in out
