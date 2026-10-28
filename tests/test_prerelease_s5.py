"""Pre-release §5 findings: merge landing from a delegate worktree."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from tests.helpers import REPO
from tests.review_repo_helpers import commit_file, git, make_review_repo

from specy_road.bundled_scripts import finish_task


def _finish(repo: Path) -> int:
    with pytest.raises(SystemExit) as e:
        finish_task.main(["--repo-root", str(repo)])
        raise SystemExit(0)
    return e.value.code or 0


def _delegate_layout(tmp_path: Path, monkeypatch) -> tuple[Path, Path, Path]:
    """Coordinator checkout on ``dev``; the leaf in a linked worktree; a bare origin."""
    monkeypatch.setenv("PYTHONPATH", str(REPO))   # finish runs validate/export/digest as subprocesses
    repo = make_review_repo(tmp_path)
    git(repo, "checkout", "-q", "dev")
    commit_file(repo, "roadmap/git-workflow.yaml",
                "version: 1\nintegration_branch: dev\nremote: origin\non_complete: merge\n", "merge mode")
    commit_file(repo, ".gitignore", "work/reviews/\n.specyrd/cache/\n", "as init project scaffolds")
    git(repo, "checkout", "-q", "feature/rm-thing")
    git(repo, "merge", "-q", "--no-edit", "dev")
    git(repo, "checkout", "-q", "dev")
    bare = tmp_path / "remote.git"
    git(tmp_path, "clone", "-q", "--bare", str(repo), str(bare))
    git(repo, "remote", "add", "origin", str(bare))
    git(repo, "fetch", "-q", "origin")
    leaf = tmp_path / "leaf"
    git(repo, "worktree", "add", "-q", str(leaf), "feature/rm-thing")
    return repo, leaf, bare


def test_finish_lands_merge_in_the_worktree_that_holds_the_integration_branch(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    repo, leaf, bare = _delegate_layout(tmp_path, monkeypatch)
    assert _finish(leaf) == 0
    assert "[ok] merged feature/rm-thing into dev and pushed to origin" in capsys.readouterr().out
    tip = git(leaf, "rev-parse", "feature/rm-thing")
    git(bare, "merge-base", "--is-ancestor", tip, "dev")
    assert git(repo, "rev-parse", "HEAD") == git(bare, "rev-parse", "dev")
    assert git(repo, "status", "--porcelain") == ""
    assert git(leaf, "status", "--porcelain") == ""


def test_finish_refuses_before_bookkeeping_when_that_worktree_is_dirty(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    repo, leaf, _bare = _delegate_layout(tmp_path, monkeypatch)
    before = git(leaf, "rev-parse", "HEAD")
    (repo / "roadmap" / "git-workflow.yaml").write_text("# coordinator edit\n")
    assert _finish(leaf) == 1
    assert f"'dev' is checked out in {repo} with uncommitted changes" in capsys.readouterr().err
    assert git(leaf, "rev-parse", "HEAD") == before
    assert git(repo, "status", "--porcelain") == "M roadmap/git-workflow.yaml"
    git(repo, "checkout", "--", "roadmap/git-workflow.yaml")
    git(repo, "checkout", "-q", "--detach")
    holder = tmp_path / "holder"
    git(repo, "worktree", "add", "-q", str(holder), "dev")
    shutil.rmtree(holder)   # still listed as holding dev; git status cannot run there
    assert _finish(leaf) == 1
    assert f"could not read the status of {holder}" in capsys.readouterr().err
    assert git(leaf, "rev-parse", "HEAD") == before


def test_abort_from_a_delegated_leaf_refuses_cleanly_while_the_base_is_held_elsewhere(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    # §5 re-check F-R2: abort from the leaf's worktree crashed in `git checkout dev`.
    from specy_road.bundled_scripts import abort_task_pickup

    repo, leaf, bare = _delegate_layout(tmp_path, monkeypatch)
    before = git(bare, "rev-parse", "dev")
    with pytest.raises(SystemExit) as e:
        abort_task_pickup.main(["--repo-root", str(leaf)])
    err = capsys.readouterr().err
    assert e.value.code == 1 and f"'dev' is checked out in {repo}" in err and "git worktree remove" in err
    assert git(leaf, "branch", "--show-current") == "feature/rm-thing" and git(bare, "rev-parse", "dev") == before
