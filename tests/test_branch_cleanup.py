"""Merged feature branches: ``finish-this-task --delete-branch`` and ``branches prune``.

Both delete only what the integration branch already contains, and prune also
leaves a merged-looking branch alone while something still uses it: a registry
claim (a fresh pickup's tip *is* an integration commit) or an open milestone
rollup.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from specy_road import cli
from specy_road.bundled_scripts import branches_cli, finish_task
from tests.helpers import REPO
from tests.review_repo_helpers import commit_file, git, make_review_repo

BR = "feature/rm-thing"


def _exit(fn, argv: list[str]) -> int:
    with pytest.raises(SystemExit) as e:
        fn(argv)
        raise SystemExit(0)
    return e.value.code or 0


def _merge_mode_repo(tmp_path: Path, monkeypatch) -> tuple[Path, Path]:
    """The claimed leaf, mergeable into ``dev``, with a bare origin holding both branches."""
    monkeypatch.setenv("PYTHONPATH", str(REPO))   # finish runs validate/export/digest as subprocesses
    repo = make_review_repo(tmp_path)
    git(repo, "checkout", "-q", "dev")
    commit_file(repo, "roadmap/git-workflow.yaml",
                "version: 1\nintegration_branch: dev\nremote: origin\non_complete: merge\n", "merge mode")
    commit_file(repo, ".gitignore", "work/reviews/\n.specyrd/cache/\n", "as init project scaffolds")
    git(repo, "checkout", "-q", BR)
    git(repo, "merge", "-q", "--no-edit", "dev")
    bare = tmp_path / "remote.git"
    git(tmp_path, "clone", "-q", "--bare", str(repo), str(bare))
    git(bare, "symbolic-ref", "HEAD", "refs/heads/dev")   # a remote refuses to delete its HEAD branch
    git(repo, "remote", "add", "origin", str(bare))
    git(repo, "fetch", "-q", "origin")
    return repo, bare


def _has_branch(repo: Path, ref: str) -> bool:
    return bool(git(repo, "for-each-ref", "--format=%(refname)", ref))


# --- finish-this-task --delete-branch ------------------------------------------


@pytest.mark.parametrize("delegated", [False, True], ids=["same-checkout", "delegate-worktree"])
def test_finish_delete_branch_deletes_it_locally_and_on_the_remote(
    tmp_path: Path, monkeypatch, capsys, delegated: bool
) -> None:
    repo, bare = _merge_mode_repo(tmp_path, monkeypatch)
    here = repo
    if delegated:   # dev held by the coordinator checkout, the leaf in a linked worktree
        git(repo, "checkout", "-q", "dev")
        here = tmp_path / "leaf"
        git(repo, "worktree", "add", "-q", str(here), BR)

    assert _exit(finish_task.main, ["--delete-branch", "--repo-root", str(here)]) == 0

    out = capsys.readouterr().out
    assert f"[ok] merged {BR} into dev and pushed to origin" in out
    assert f"[ok] deleted {BR} on origin" in out
    assert not _has_branch(repo, f"refs/heads/{BR}")
    assert not _has_branch(bare, f"refs/heads/{BR}")
    if delegated:
        assert f"[ok] deleted local branch {BR}; this checkout is now detached at dev" in out
        assert git(here, "rev-parse", "HEAD") == git(bare, "rev-parse", "dev")
    else:
        assert f"[ok] deleted local branch {BR}; this checkout is now on dev" in out
        assert git(repo, "branch", "--show-current") == "dev"


def test_finish_delete_branch_is_refused_under_pr_before_any_bookkeeping(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    repo, _bare = _merge_mode_repo(tmp_path, monkeypatch)
    before = git(repo, "rev-parse", "HEAD")

    code = _exit(finish_task.main, ["--on-complete", "pr", "--delete-branch", "--repo-root", str(repo)])

    assert code == 1
    assert "--delete-branch needs a merge landing" in capsys.readouterr().err
    assert git(repo, "rev-parse", "HEAD") == before
    assert git(repo, "branch", "--show-current") == BR


# --- branches prune ------------------------------------------------------------


def _branch_with_commit(repo: Path, branch: str, rel: str) -> None:
    git(repo, "checkout", "-q", "-b", branch, "dev")
    commit_file(repo, rel, "x\n", branch)
    git(repo, "checkout", "-q", "dev")


@pytest.fixture
def prune_repo(tmp_path: Path) -> tuple[Path, Path]:
    """``dev`` contains rm-done, rm-gone (remote only), fix/merged, the claimed
    rm-thing and the open rollup rm-roll; it lacks rm-open."""
    repo = make_review_repo(tmp_path)
    git(repo, "checkout", "-q", "dev")
    chunk = repo / "roadmap" / "phases" / "M1.json"
    doc = json.loads(chunk.read_text())
    doc["nodes"][0]["milestone_execution"] = {"state": "active", "rollup_branch": "feature/rm-roll"}
    commit_file(repo, "roadmap/phases/M1.json", json.dumps(doc), "milestone session")
    git(repo, "branch", "feature/rm-roll")
    for branch in ("feature/rm-done", "feature/rm-gone", "fix/merged", "feature/rm-open"):
        _branch_with_commit(repo, branch, f"src/{branch.rsplit('/', 1)[1]}.py")
    for branch in ("feature/rm-done", "feature/rm-gone", "fix/merged", BR):
        git(repo, "merge", "-q", "--no-ff", "--no-edit", branch)
    bare = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", str(bare))
    git(repo, "remote", "add", "origin", str(bare))
    git(repo, "push", "-q", "origin", "--all")
    git(repo, "branch", "-q", "-D", "feature/rm-gone")
    return repo, bare


KEPT = ("feature/rm-thing", "feature/rm-roll", "feature/rm-open", "fix/merged")


def test_prune_lists_merged_unclaimed_branches_and_deletes_nothing(prune_repo, capfd) -> None:
    repo, bare = prune_repo

    code = _exit(cli.main, ["branches", "prune", "--repo-root", str(repo)])

    out = capfd.readouterr().out
    assert code == 0
    assert "Merged into origin/dev and unclaimed:" in out
    assert "local     feature/rm-done" in out
    assert "origin    feature/rm-done" in out
    assert "origin    feature/rm-gone" in out
    for branch in KEPT:
        assert branch not in out
    assert _has_branch(repo, "refs/heads/feature/rm-done")
    assert _has_branch(bare, "refs/heads/feature/rm-gone")


def test_prune_delete_removes_only_the_listed_branches(prune_repo, capsys) -> None:
    repo, bare = prune_repo

    assert _exit(branches_cli.main, ["branches", "prune", "--delete", "--repo-root", str(repo)]) == 0

    out = capsys.readouterr().out
    assert "[ok] deleted local branch feature/rm-done" in out
    assert "[ok] deleted feature/rm-gone on origin" in out
    assert not _has_branch(repo, "refs/heads/feature/rm-done")
    for gone in ("feature/rm-done", "feature/rm-gone"):
        assert not _has_branch(bare, f"refs/heads/{gone}")
    for branch in KEPT:
        assert _has_branch(repo, f"refs/heads/{branch}")
        assert _has_branch(bare, f"refs/heads/{branch}")
    assert _exit(branches_cli.main, ["branches", "prune", "--repo-root", str(repo)]) == 0
    assert "Nothing to prune" in capsys.readouterr().out


def test_prune_refuses_without_a_fresh_fetch(prune_repo, capsys) -> None:
    repo, bare = prune_repo
    git(repo, "remote", "set-url", "origin", str(bare.parent / "missing.git"))

    code = _exit(branches_cli.main, ["branches", "prune", "--delete", "--repo-root", str(repo)])

    assert code == 1
    assert "git fetch --prune origin failed" in capsys.readouterr().err
    assert _has_branch(repo, "refs/heads/feature/rm-done")
