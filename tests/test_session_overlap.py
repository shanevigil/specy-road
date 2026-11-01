"""`session start` / `touch` overlap warnings name the other worktree and its edit state (M4.15)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from tests.review_repo_helpers import git, make_review_repo

from specy_road import session_presence as sp
from specy_road.bundled_scripts import session_cli


def _cli(*args: str) -> int:
    with pytest.raises(SystemExit) as e:
        session_cli.main(list(args))
    return e.value.code or 0


def _other_worktree(tmp_path: Path, repo: Path, branch: str = "feature/other") -> Path:
    """A linked worktree on a new branch from ``dev``: none of the feature branch's commits."""
    wt = tmp_path / "wt"
    git(repo, "worktree", "add", "-q", "-b", branch, str(wt), "dev")
    return wt.resolve()


def _start_as(monkeypatch, user: str, repo: Path, *args: str, cmd: str = "start") -> int:
    monkeypatch.setenv("USER", user)
    return _cli("session", cmd, *args, "--repo-root", str(repo))


def test_warning_names_worktree_branch_and_uncommitted_edits(tmp_path: Path, capsys, monkeypatch) -> None:
    repo = make_review_repo(tmp_path)
    wt = _other_worktree(tmp_path, repo)
    (wt / "src").mkdir(exist_ok=True)
    (wt / "src" / "c.py").write_text("c\n")       # untracked, inside the overlap
    (wt / "notes.txt").write_text("n\n")         # untracked, outside it
    monkeypatch.setenv("USER", "alice")
    sp.start_session(repo, "alice", paths=["src"], worktree=wt)
    monkeypatch.chdir(repo)
    assert _start_as(monkeypatch, "bob", repo, "--agent", "bob", "--path", "src/c.py") == 0
    err = capsys.readouterr().err
    assert "overlap live session 'alice' on feature/other" in err
    assert f"user 'alice': worktree {wt}, branch feature/other" in err
    assert "edits there: uncommitted: src/c.py" in err and "notes.txt" not in err
    assert "committed, not merged" not in err


def test_warning_reports_committed_edits_not_merged(tmp_path: Path, capsys, monkeypatch) -> None:
    repo = make_review_repo(tmp_path)  # feature/rm-thing commits src/a.py and docs/x.md on top of dev
    monkeypatch.setenv("USER", "alice")
    sp.start_session(repo, "alice", paths=["src", "docs"], worktree=repo)
    wt = _other_worktree(tmp_path, repo)
    monkeypatch.chdir(wt)
    assert _start_as(monkeypatch, "bob", repo, "--agent", "bob", "--path", "src") == 0
    err = capsys.readouterr().err
    assert f"worktree {repo}, branch feature/rm-thing" in err
    assert "edits there: committed, not merged into dev: src/a.py" in err
    assert "docs/x.md" not in err and "uncommitted" not in err


def test_warning_says_neither_when_the_other_copy_is_clean(tmp_path: Path, capsys, monkeypatch) -> None:
    repo = make_review_repo(tmp_path)
    wt = _other_worktree(tmp_path, repo)
    monkeypatch.setenv("USER", "alice")
    sp.start_session(repo, "alice", paths=["src"], worktree=wt)
    monkeypatch.chdir(repo)
    assert _start_as(monkeypatch, "bob", repo, "--agent", "bob", "--path", "src/a.py") == 0
    assert "edits there: neither uncommitted nor unmerged into dev on the overlapping paths" in capsys.readouterr().err


def test_own_session_in_another_worktree_is_reported_as_yours_on_touch(tmp_path: Path, capsys, monkeypatch) -> None:
    repo = make_review_repo(tmp_path)
    wt = _other_worktree(tmp_path, repo)
    (wt / "src" / "a.py").parent.mkdir(exist_ok=True)
    (wt / "src" / "a.py").write_text("mine, elsewhere\n")
    monkeypatch.setenv("USER", "carol")
    sp.start_session(repo, "carol-s1", paths=["src/a.py"], worktree=wt)
    monkeypatch.chdir(repo)
    assert _start_as(monkeypatch, "carol", repo, "--agent", "carol-s2") == 0
    capsys.readouterr()
    assert _start_as(monkeypatch, "carol", repo, "--agent", "carol-s2", "--path", "src", cmd="touch") == 0
    err = capsys.readouterr().err
    assert "overlap live session 'carol-s1'" in err
    assert f"yours: worktree {wt}, branch feature/other" in err
    assert "edits there: uncommitted: src/a.py" in err


def test_a_removed_worktree_is_unknown_not_clean(tmp_path: Path, capsys, monkeypatch) -> None:
    repo = make_review_repo(tmp_path)
    wt = _other_worktree(tmp_path, repo)
    monkeypatch.setenv("USER", "alice")
    sp.start_session(repo, "alice", paths=["src"], worktree=wt)
    shutil.rmtree(wt)
    monkeypatch.chdir(repo)
    assert _start_as(monkeypatch, "bob", repo, "--agent", "bob", "--path", "src") == 0
    err = capsys.readouterr().err
    assert f"edits there: unknown (no git checkout at {wt})" in err and "neither" not in err
