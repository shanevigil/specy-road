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
from specy_road.bundled_scripts.grind_session_cleanup import delete_remote_branch
from specy_road.milestone_session import milestone_session_path, write_milestone_session
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


@pytest.mark.parametrize(
    "delegated, on_remote",
    [(False, True), (True, True), (False, False)],
    ids=["same-checkout", "delegate-worktree", "never-pushed"],
)
def test_finish_delete_branch_deletes_it_locally_and_on_the_remote(
    tmp_path: Path, monkeypatch, capsys, delegated: bool, on_remote: bool
) -> None:
    repo, bare = _merge_mode_repo(tmp_path, monkeypatch)
    if not on_remote:
        git(bare, "branch", "-D", BR)
        git(repo, "fetch", "-q", "--prune", "origin")
    here = repo
    if delegated:   # dev held by the coordinator checkout, the leaf in a linked worktree
        git(repo, "checkout", "-q", "dev")
        here = tmp_path / "leaf"
        git(repo, "worktree", "add", "-q", str(here), BR)

    assert _exit(finish_task.main, ["--delete-branch", "--repo-root", str(here)]) == 0

    out, err = capsys.readouterr()
    assert f"[ok] merged {BR} into dev and pushed to origin" in out
    assert (f"[ok] deleted {BR} on origin" in out) is on_remote
    assert "--delete-branch:" not in err   # a branch never pushed has nothing to delete there
    assert not _has_branch(repo, f"refs/heads/{BR}")
    assert not _has_branch(bare, f"refs/heads/{BR}")
    if delegated:
        assert f"[ok] deleted local branch {BR}; this checkout is now detached at dev" in out
        assert git(here, "rev-parse", "HEAD") == git(bare, "rev-parse", "dev")
    else:
        assert f"[ok] deleted local branch {BR}; this checkout is now on dev" in out
        assert git(repo, "branch", "--show-current") == "dev"


def test_a_retried_landing_deletes_the_branch(tmp_path: Path, monkeypatch, capsys) -> None:
    """The bookkeeping commit already exists; the re-run only lands, and still deletes."""
    repo, bare = _merge_mode_repo(tmp_path, monkeypatch)
    hook = bare / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\nexit 1\n")
    hook.chmod(0o755)

    assert _exit(finish_task.main, ["--delete-branch", "--repo-root", str(repo)]) == 1

    err = capsys.readouterr().err
    assert "finish-this-task --on-complete merge --delete-branch" in err
    assert _has_branch(repo, f"refs/heads/{BR}")
    assert _has_branch(bare, f"refs/heads/{BR}")
    hook.unlink()

    assert _exit(finish_task.main, ["--delete-branch", "--repo-root", str(repo)]) == 0

    out = capsys.readouterr().out
    assert f"[ok] merged {BR} into dev and pushed to origin" in out
    assert f"[ok] deleted {BR} on origin" in out
    assert not _has_branch(repo, f"refs/heads/{BR}")
    assert not _has_branch(bare, f"refs/heads/{BR}")


def _rollup_repo(tmp_path: Path, monkeypatch) -> tuple[Path, Path]:
    """A leaf under an open milestone, with the rollup branch and a bare origin.

    ``on_complete`` stays ``pr``: the rollup landing is what merges the leaf,
    so ``--delete-branch`` must not be refused the way a plain ``pr`` finish is.
    """
    monkeypatch.setenv("PYTHONPATH", str(REPO))
    repo = make_review_repo(tmp_path)
    git(repo, "checkout", "-q", "dev")
    chunk = repo / "roadmap" / "phases" / "M1.json"
    doc = json.loads(chunk.read_text())
    leaf = doc["nodes"][0]
    leaf["parent_id"] = "M1"
    parent = {
        "id": "M1", "node_key": "22222222-2222-5222-8222-222222222222",
        "codename": "roll", "title": "Roll", "type": "milestone",
        "parent_id": None, "sibling_order": 1, "status": "In Progress",
        "dependencies": [], "touch_zones": [], "goal": "Roll the leaves up.",
        "planning_dir": "planning/M1_roll_22222222-2222-5222-8222-222222222222.md",
        "milestone_execution": {
            "state": "active", "rollup_branch": "feature/rm-roll",
            "integration_branch": "dev", "remote": "origin",
        },
    }
    doc["nodes"] = [parent, leaf]
    commit_file(repo, "roadmap/phases/M1.json", json.dumps(doc), "parent milestone")
    commit_file(repo, parent["planning_dir"], "# M1 Roll\n\n## Intent\n\nRoll up.\n", "parent sheet")
    commit_file(repo, "roadmap/git-workflow.yaml",
                "version: 1\nintegration_branch: dev\nremote: origin\non_complete: pr\n",
                "pr mode")
    git(repo, "branch", "feature/rm-roll")
    git(repo, "checkout", "-q", BR)
    git(repo, "merge", "-q", "--no-edit", "dev")
    write_milestone_session(
        milestone_session_path(repo / "work"),
        parent_node_id="M1", parent_codename="roll",
        integration_branch="dev", remote="origin",
    )
    bare = tmp_path / "remote.git"
    git(tmp_path, "clone", "-q", "--bare", str(repo), str(bare))
    git(bare, "symbolic-ref", "HEAD", "refs/heads/dev")
    git(repo, "remote", "add", "origin", str(bare))
    git(repo, "fetch", "-q", "origin")
    return repo, bare


def test_rollup_finish_deletes_the_leaf_once_it_is_in_the_rollup(
    tmp_path: Path, monkeypatch, capsys,
) -> None:
    repo, bare = _rollup_repo(tmp_path, monkeypatch)
    leaf = git(repo, "rev-parse", BR)

    assert _exit(finish_task.main, ["--delete-branch", "--repo-root", str(repo)]) == 0

    out = capsys.readouterr().out
    assert "[ok] Milestone rollup: integration branch updated; rollup branch merged." in out
    assert f"[ok] deleted {BR} on origin" in out
    assert not _has_branch(repo, f"refs/heads/{BR}")
    assert not _has_branch(bare, f"refs/heads/{BR}")
    assert _has_branch(repo, "refs/heads/feature/rm-roll")
    git(repo, "merge-base", "--is-ancestor", leaf, "feature/rm-roll")
    assert git(repo, "branch", "--show-current") == "dev"


def test_a_retried_rollup_landing_deletes_the_leaf(tmp_path: Path, monkeypatch, capsys) -> None:
    """Bookkeeping is committed and the rollup merge failed; the re-run deletes."""
    repo, bare = _rollup_repo(tmp_path, monkeypatch)
    hook = bare / "hooks" / "pre-receive"
    hook.write_text(
        "#!/bin/sh\n"
        "while read old new ref; do\n"
        "  case $ref in refs/heads/feature/rm-roll) exit 1 ;; esac\n"
        "done\n"
        "exit 0\n",
    )
    hook.chmod(0o755)
    assert _exit(finish_task.main, ["--delete-branch", "--repo-root", str(repo)]) == 1
    assert _has_branch(repo, f"refs/heads/{BR}")
    hook.unlink()
    capsys.readouterr()
    git(repo, "checkout", "-q", BR)  # the failed push left this checkout on dev

    assert _exit(finish_task.main, ["--delete-branch", "--repo-root", str(repo)]) == 0

    out = capsys.readouterr().out
    assert "landing it on feature/rm-roll" in out
    assert f"[ok] deleted {BR} on origin" in out
    assert not _has_branch(bare, f"refs/heads/{BR}")
    assert _has_branch(repo, "refs/heads/feature/rm-roll")


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


def test_prune_delete_reports_a_refused_delete_and_exits_1(prune_repo, capsys) -> None:
    repo, bare = prune_repo
    git(repo, "checkout", "-q", "feature/rm-done")   # git branch -d refuses the checked-out branch

    code = _exit(branches_cli.main, ["branches", "prune", "--delete", "--repo-root", str(repo)])

    assert code == 1
    assert "[warn] feature/rm-done:" in capsys.readouterr().err
    assert _has_branch(repo, "refs/heads/feature/rm-done")
    assert not _has_branch(bare, "refs/heads/feature/rm-done")


def test_a_moved_remote_tip_is_not_deleted(prune_repo, tmp_path: Path) -> None:
    """The merged check saw the old tip; a push before the delete must survive it.

    finish and prune both delete through ``delete_remote_branch``, which leases
    the delete to that tip.
    """
    repo, bare = prune_repo
    branch = "feature/rm-done"
    checked = git(repo, "rev-parse", f"origin/{branch}")
    other = tmp_path / "other"
    git(tmp_path, "clone", "-q", "-b", branch, str(bare), str(other))
    git(other, "config", "user.email", "t@e.com")
    git(other, "config", "user.name", "T")
    commit_file(other, "src/later.py", "y\n", "after the check")
    git(other, "push", "-q", "origin", branch)

    failure = delete_remote_branch(repo, branch, "origin/dev", "origin")

    assert failure is not None and failure["step"] == "push_delete"
    assert "stale info" in failure["message"]
    assert git(bare, "rev-parse", branch) != checked
    assert _has_branch(bare, f"refs/heads/{branch}")


def test_prune_keeps_a_rollup_the_remote_still_marks_active(tmp_path: Path, capsys) -> None:
    """The working tree is behind origin; its roadmap does not list the rollup."""
    repo = make_review_repo(tmp_path)
    git(repo, "checkout", "-q", "dev")
    bare = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", str(bare))
    git(bare, "symbolic-ref", "HEAD", "refs/heads/dev")
    git(repo, "remote", "add", "origin", str(bare))
    git(repo, "push", "-q", "origin", "dev")
    chunk = repo / "roadmap" / "phases" / "M1.json"
    doc = json.loads(chunk.read_text())
    doc["nodes"][0]["milestone_execution"] = {
        "state": "active", "rollup_branch": "feature/rm-roll",
    }
    commit_file(repo, "roadmap/phases/M1.json", json.dumps(doc), "open the rollup")
    git(repo, "branch", "feature/rm-roll")
    git(repo, "push", "-q", "origin", "dev", "feature/rm-roll")
    git(repo, "reset", "-q", "--hard", "HEAD~1")

    code = _exit(branches_cli.main, ["branches", "prune", "--delete", "--repo-root", str(repo)])

    assert code == 0
    out = capsys.readouterr().out
    assert "feature/rm-roll" not in out
    assert _has_branch(repo, "refs/heads/feature/rm-roll")
    assert _has_branch(bare, "refs/heads/feature/rm-roll")


def test_prune_refuses_without_a_fresh_fetch(prune_repo, capsys) -> None:
    repo, bare = prune_repo
    git(repo, "remote", "set-url", "origin", str(bare.parent / "missing.git"))

    code = _exit(branches_cli.main, ["branches", "prune", "--delete", "--repo-root", str(repo)])

    assert code == 1
    assert "git fetch --prune origin failed" in capsys.readouterr().err
    assert _has_branch(repo, "refs/heads/feature/rm-done")
