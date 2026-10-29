"""Milestone-rollup landings delete the leaf and refuse a tip that moved.

A rollup finish merges the leaf into ``feature/rm-<parent>``, not into the
integration branch, so the delete checks the rollup ref. A retry lands only
the finish bookkeeping commit, and ``--no-milestone-rollup`` skips that retry.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from specy_road.bundled_scripts import finish_task
from specy_road.milestone_session import milestone_session_path, write_milestone_session
from tests.helpers import REPO
from tests.review_repo_helpers import commit_file, git, make_review_repo

BR = "feature/rm-thing"


def _exit(fn, argv: list[str]) -> int:
    try:
        fn(argv)
    except SystemExit as exc:
        return int(exc.code or 0)
    return 0


def _has_branch(repo: Path, ref: str) -> bool:
    try:
        git(repo, "show-ref", "--verify", "--quiet", ref)
    except subprocess.CalledProcessError:
        return False
    return True


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


def _reject_rollup_push(bare: Path) -> Path:
    hook = bare / "hooks" / "pre-receive"
    hook.write_text(
        "#!/bin/sh\n"
        "while read old new ref; do\n"
        "  case $ref in refs/heads/feature/rm-roll) exit 1 ;; esac\n"
        "done\n"
        "exit 0\n",
    )
    hook.chmod(0o755)
    return hook


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
    hook = _reject_rollup_push(bare)
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


def test_a_retry_refuses_commits_added_after_the_finish_commit(
    tmp_path: Path, monkeypatch, capsys,
) -> None:
    repo, bare = _rollup_repo(tmp_path, monkeypatch)
    hook = _reject_rollup_push(bare)
    assert _exit(finish_task.main, ["--repo-root", str(repo)]) == 1
    hook.unlink()
    capsys.readouterr()
    git(repo, "checkout", "-q", BR)
    late = commit_file(repo, "src/late.py", "x = 2\n", "after review")
    remote_rollup = git(bare, "rev-parse", "feature/rm-roll")

    assert _exit(finish_task.main, ["--repo-root", str(repo)]) == 1

    assert "moved past its finish-this-task commit" in capsys.readouterr().err
    assert git(bare, "rev-parse", "feature/rm-roll") == remote_rollup
    with pytest.raises(subprocess.CalledProcessError):
        git(repo, "merge-base", "--is-ancestor", late, "feature/rm-roll")


def test_a_repeat_finish_with_no_milestone_rollup_does_not_land_the_rollup(
    tmp_path: Path, monkeypatch, capsys,
) -> None:
    repo, bare = _rollup_repo(tmp_path, monkeypatch)
    hook = _reject_rollup_push(bare)
    assert _exit(finish_task.main, ["--repo-root", str(repo)]) == 1
    hook.unlink()
    capsys.readouterr()
    git(repo, "checkout", "-q", BR)
    remote_rollup = git(bare, "rev-parse", "feature/rm-roll")

    code = _exit(finish_task.main, ["--no-milestone-rollup", "--repo-root", str(repo)])

    out = capsys.readouterr().out
    assert code == 0
    assert "landing it on feature/rm-roll" not in out
    assert "Do not run finish again" in out
    assert git(bare, "rev-parse", "feature/rm-roll") == remote_rollup
