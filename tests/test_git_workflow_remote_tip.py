"""Tests for git_remote_tip_author and registry enrichment remote_tip kind."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

import roadmap_gui_remote as rgr

from specy_road.git_workflow_config import (
    git_branch_tip_author,
    git_local_branch_tip_author,
    git_remote_tip_author,
)


def _run_git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def test_git_remote_tip_author_from_remote_tracking_ref(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _run_git(repo, "init")
    _run_git(repo, "config", "user.email", "t@example.com")
    _run_git(repo, "config", "user.name", "InitCommitter")
    f = repo / "f.txt"
    f.write_text("a\n", encoding="utf-8")
    _run_git(repo, "add", "f.txt")
    _run_git(repo, "commit", "-m", "init")
    _run_git(repo, "branch", "-M", "main")
    _run_git(repo, "checkout", "-b", "feature/rm-tipcase")
    f.write_text("a\nb\n", encoding="utf-8")
    env = {**os.environ, "GIT_AUTHOR_NAME": "Alice Tip", "GIT_AUTHOR_EMAIL": "a@example.com"}
    subprocess.run(
        ["git", "commit", "-am", "wip"],
        cwd=repo,
        check=True,
        capture_output=True,
        env=env,
    )
    # Simulate refs/remotes/origin/feature/rm-tipcase after fetch (no network).
    tip = subprocess.run(
        ["git", "rev-parse", "feature/rm-tipcase"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    _run_git(repo, "update-ref", f"refs/remotes/origin/feature/rm-tipcase", tip)
    _run_git(repo, "checkout", "main")

    assert git_remote_tip_author(repo, "origin", "feature/rm-tipcase") == "Alice Tip"
    assert git_remote_tip_author(repo, "origin", "missing-branch") is None


def test_git_local_branch_tip_author_from_refs_heads(tmp_path: Path) -> None:
    repo = tmp_path / "repo_local_head"
    repo.mkdir()
    _run_git(repo, "init")
    _run_git(repo, "config", "user.email", "t@example.com")
    _run_git(repo, "config", "user.name", "InitCommitter")
    f = repo / "f.txt"
    f.write_text("a\n", encoding="utf-8")
    _run_git(repo, "add", "f.txt")
    _run_git(repo, "commit", "-m", "init")
    _run_git(repo, "branch", "-M", "main")
    _run_git(repo, "checkout", "-b", "feature/rm-localonly")
    f.write_text("a\nb\n", encoding="utf-8")
    env = {**os.environ, "GIT_AUTHOR_NAME": "Dana Local", "GIT_AUTHOR_EMAIL": "d@example.com"}
    subprocess.run(
        ["git", "commit", "-am", "wip"],
        cwd=repo,
        check=True,
        capture_output=True,
        env=env,
    )
    _run_git(repo, "checkout", "main")

    assert git_local_branch_tip_author(repo, "feature/rm-localonly") == "Dana Local"
    assert git_local_branch_tip_author(repo, "missing-branch") is None


def test_git_branch_tip_author_falls_back_to_local_when_no_remote_ref(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo_fallback"
    repo.mkdir()
    _run_git(repo, "init")
    _run_git(repo, "config", "user.email", "t@example.com")
    _run_git(repo, "config", "user.name", "InitCommitter")
    (repo / "x.txt").write_text("1\n", encoding="utf-8")
    _run_git(repo, "add", "x.txt")
    _run_git(repo, "commit", "-m", "init")
    _run_git(repo, "branch", "-M", "main")
    _run_git(repo, "checkout", "-b", "feature/rm-fallback")
    (repo / "x.txt").write_text("1\n2\n", encoding="utf-8")
    env = {**os.environ, "GIT_AUTHOR_NAME": "Eve", "GIT_AUTHOR_EMAIL": "e@example.com"}
    subprocess.run(
        ["git", "commit", "-am", "x"],
        cwd=repo,
        check=True,
        capture_output=True,
        env=env,
    )
    _run_git(repo, "checkout", "main")
    assert git_branch_tip_author(repo, "origin", "feature/rm-fallback") == "Eve"


def test_build_registry_enrichment_remote_tip_kind(tmp_path: Path) -> None:
    repo = tmp_path / "repo2"
    repo.mkdir()
    _run_git(repo, "init")
    _run_git(repo, "config", "user.email", "t@example.com")
    _run_git(repo, "config", "user.name", "Bob")
    (repo / "x.txt").write_text("1\n", encoding="utf-8")
    _run_git(repo, "add", "x.txt")
    _run_git(repo, "commit", "-m", "init")
    _run_git(repo, "branch", "-M", "main")
    _run_git(repo, "checkout", "-b", "feature/rm-enrich")
    (repo / "x.txt").write_text("1\n2\n", encoding="utf-8")
    env = {**os.environ, "GIT_AUTHOR_NAME": "Carol", "GIT_AUTHOR_EMAIL": "c@example.com"}
    subprocess.run(
        ["git", "commit", "-am", "x"],
        cwd=repo,
        check=True,
        capture_output=True,
        env=env,
    )
    tip = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    _run_git(repo, "update-ref", "refs/remotes/origin/feature/rm-enrich", tip)
    _run_git(repo, "checkout", "main")

    by_reg = {
        "N1": {"node_id": "N1", "branch": "feature/rm-enrich", "codename": "enrich"},
    }
    gr: dict = {}
    out = rgr.build_registry_enrichment(by_reg, gr, repo_root=repo, remote="origin")
    assert out["N1"]["kind"] == "remote_tip"
    assert out["N1"]["author"] == "Carol"
    assert "feature/rm-enrich" in str(out["N1"].get("hint_line", ""))


def test_build_registry_enrichment_remote_tip_from_local_branch_only(
    tmp_path: Path,
) -> None:
    """No refs/remotes/.../branch; local refs/heads/branch still yields remote_tip + author."""
    repo = tmp_path / "repo3"
    repo.mkdir()
    _run_git(repo, "init")
    _run_git(repo, "config", "user.email", "t@example.com")
    _run_git(repo, "config", "user.name", "Bob")
    (repo / "y.txt").write_text("1\n", encoding="utf-8")
    _run_git(repo, "add", "y.txt")
    _run_git(repo, "commit", "-m", "init")
    _run_git(repo, "branch", "-M", "main")
    _run_git(repo, "checkout", "-b", "feature/rm-localtip")
    (repo / "y.txt").write_text("1\n2\n", encoding="utf-8")
    env = {**os.environ, "GIT_AUTHOR_NAME": "Frank", "GIT_AUTHOR_EMAIL": "f@example.com"}
    subprocess.run(
        ["git", "commit", "-am", "y"],
        cwd=repo,
        check=True,
        capture_output=True,
        env=env,
    )
    _run_git(repo, "checkout", "main")

    by_reg = {
        "N2": {"node_id": "N2", "branch": "feature/rm-localtip", "codename": "localtip"},
    }
    gr: dict = {}
    out = rgr.build_registry_enrichment(by_reg, gr, repo_root=repo, remote="origin")
    assert out["N2"]["kind"] == "remote_tip"
    assert out["N2"]["author"] == "Frank"


def test_build_registry_enrichment_prefers_open_pr_over_remote_tip(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """When fetch_branch_enrichment returns a PR dict, remote_tip is not used."""

    def fake_fetch(_gr: dict, _br: str) -> dict:
        return {"kind": "github_pr", "author": "prauthor", "title": "t"}

    monkeypatch.setattr(rgr, "fetch_branch_enrichment", fake_fetch)
    out = rgr.build_registry_enrichment(
        {"X": {"branch": "feature/x", "node_id": "X"}},
        {"provider": "github", "repo": "o/r", "token": "t"},
        repo_root=tmp_path,
        remote="origin",
    )
    assert out["X"]["kind"] == "github_pr"
    assert out["X"]["author"] == "prauthor"
