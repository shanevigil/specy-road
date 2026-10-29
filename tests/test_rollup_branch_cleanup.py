"""Milestone-rollup landings delete the leaf and refuse a tip that moved.

A rollup finish merges the leaf into ``feature/rm-<parent>``, not into the
integration branch, so the delete checks the rollup ref. A retry lands only
the finish bookkeeping commit, and ``--no-milestone-rollup`` skips that retry.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from specy_road.bundled_scripts import finish_task
from specy_road.milestone_session import milestone_session_path, write_milestone_session
from tests.helpers import DOGFOOD, REPO
from tests.review_repo_helpers import NODE, commit_file, git, make_review_repo

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


def _attach_rollup(project: Path, tmp_path: Path) -> Path:
    """Open milestone, rollup branch, and a bare origin. Return the bare repo.

    ``on_complete`` stays ``pr``: the rollup landing is what merges the leaf,
    so ``--delete-branch`` must not be refused the way a plain ``pr`` finish is.
    """
    git(project, "checkout", "-q", "dev")
    chunk = project / "roadmap" / "phases" / "M1.json"
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
    commit_file(project, "roadmap/phases/M1.json", json.dumps(doc), "parent milestone")
    commit_file(project, parent["planning_dir"], "# M1 Roll\n\n## Intent\n\nRoll up.\n", "parent sheet")
    commit_file(project, "roadmap/git-workflow.yaml",
                "version: 1\nintegration_branch: dev\nremote: origin\non_complete: pr\n",
                "pr mode")
    git(project, "branch", "feature/rm-roll")
    git(project, "checkout", "-q", BR)
    git(project, "merge", "-q", "--no-edit", "dev")
    write_milestone_session(
        milestone_session_path(project / "work"),
        parent_node_id="M1", parent_codename="roll",
        integration_branch="dev", remote="origin",
    )
    bare = tmp_path / "remote.git"
    source = git(project, "rev-parse", "--show-toplevel")
    git(tmp_path, "clone", "-q", "--bare", source, str(bare))
    git(bare, "symbolic-ref", "HEAD", "refs/heads/dev")
    git(project, "remote", "add", "origin", str(bare))
    git(project, "fetch", "-q", "origin")
    return bare


def _rollup_repo(tmp_path: Path, monkeypatch) -> tuple[Path, Path]:
    """A leaf under an open milestone, with the rollup branch and a bare origin."""
    monkeypatch.setenv("PYTHONPATH", str(REPO))
    repo = make_review_repo(tmp_path)
    return repo, _attach_rollup(repo, tmp_path)


def _nested_rollup_repo(tmp_path: Path, monkeypatch) -> tuple[Path, Path, Path]:
    """Git root, ``sr/`` project root, and bare origin for the same rollup leaf."""
    monkeypatch.setenv("PYTHONPATH", str(REPO))
    top = tmp_path / "checkout"
    project = top / "sr"
    (project / "roadmap" / "phases").mkdir(parents=True)
    git(top, "init", "-q", "-b", "dev")
    git(top, "config", "user.email", "t@e.com")
    git(top, "config", "user.name", "T")
    (top / ".specyrd").mkdir()
    (top / ".specyrd" / "manifest.json").write_text(
        json.dumps({"project_root": "sr"}) + "\n", encoding="utf-8",
    )
    shutil.copytree(DOGFOOD / "schemas", project / "schemas")
    rm = project / "roadmap"
    (rm / "manifest.json").write_text(
        json.dumps({"version": 1, "includes": ["phases/M1.json"]}), encoding="utf-8",
    )
    (rm / "phases" / "M1.json").write_text(json.dumps({"nodes": [NODE]}), encoding="utf-8")
    sheet = project / NODE["planning_dir"]
    sheet.parent.mkdir(parents=True)
    sheet.write_text("# M1.1 Thing\n\n## Intent\n\nDo the thing.\n", encoding="utf-8")
    (rm / "git-workflow.yaml").write_text(
        "version: 1\nintegration_branch: dev\nremote: origin\n", encoding="utf-8",
    )
    (rm / "registry.yaml").write_text(
        "version: 1\nentries:\n- codename: thing\n  node_id: M1.1\n"
        f"  branch: {BR}\n  touch_zones: [src]\n  implementation_review: pending\n",
        encoding="utf-8",
    )
    git(top, "add", "-A")
    git(top, "commit", "-qm", "graph")
    git(top, "checkout", "-q", "-b", BR)
    commit_file(project, "src/a.py", "print('a')\n", "impl")
    return top, project, _attach_rollup(project, tmp_path)


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


def test_a_nested_rollup_finish_stays_on_the_integration_branch(
    tmp_path: Path, monkeypatch, capsys,
) -> None:
    """project_root sr/: this checkout holds the integration branch, so delete must not detach."""
    top, project, bare = _nested_rollup_repo(tmp_path, monkeypatch)

    assert _exit(finish_task.main, ["--delete-branch", "--repo-root", str(project)]) == 0

    out = capsys.readouterr().out
    assert f"[ok] deleted local branch {BR}; this checkout is now on dev" in out
    assert "detached" not in out
    assert not _has_branch(project, f"refs/heads/{BR}")
    assert not _has_branch(bare, f"refs/heads/{BR}")
    assert git(top, "symbolic-ref", "HEAD") == "refs/heads/dev"
    assert git(top, "branch", "--show-current") == "dev"
