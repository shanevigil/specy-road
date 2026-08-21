"""The on-complete sidecar is removed during the bookkeeping phase.

A tracked sidecar that is merely unlinked leaves an uncommitted deletion, and
the next checkout or sync silently restores it — so a stale sidecar outlives the
task it belonged to. Removing it while the bookkeeping commit is still being
assembled means the deletion lands in that commit instead.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from specy_road.finish_work_artifacts import cleanup_session_sidecar
from specy_road.on_complete_session import (
    on_complete_session_path,
    remove_on_complete_session,
    write_on_complete_session,
)


def _git(root: Path, *args: str) -> str:
    r = subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True, text=True
    )
    return r.stdout


def _sidecar(root: Path) -> Path:
    work = root / "work"
    work.mkdir(exist_ok=True)
    path = on_complete_session_path(work, "M1.1")
    write_on_complete_session(path, node_id="M1.1", codename="cn", on_complete="merge")
    return path


def _repo(root: Path) -> None:
    _git(root, "init")
    _git(root, "config", "user.email", "a@b.c")
    _git(root, "config", "user.name", "t")
    # Another tracked path so `git checkout -- .` has a pathspec match once the
    # sidecar is gone.
    (root / "README.md").write_text("app\n", encoding="utf-8")
    _git(root, "add", "README.md")


def test_tracked_sidecar_is_returned_for_staging(tmp_path: Path) -> None:
    _repo(tmp_path)
    path = _sidecar(tmp_path)
    _git(tmp_path, "add", "-f", "work")
    _git(tmp_path, "commit", "-m", "track sidecar")

    assert cleanup_session_sidecar(tmp_path, path) == ["work/.on-complete-M1.1.yaml"]
    assert not path.exists()

    # The caller folds that path into `git add` + `git commit`; once it does,
    # the sidecar cannot come back on the next checkout.
    _git(tmp_path, "add", "work/.on-complete-M1.1.yaml")
    _git(tmp_path, "commit", "-m", "bookkeeping")
    _git(tmp_path, "checkout", "--", ".")
    assert not path.exists()
    assert _git(tmp_path, "status", "--porcelain").strip() == ""


def test_untracked_sidecar_needs_no_staging(tmp_path: Path) -> None:
    _repo(tmp_path)
    path = _sidecar(tmp_path)
    assert cleanup_session_sidecar(tmp_path, path) == []
    assert not path.exists()


def test_missing_sidecar_is_a_no_op(tmp_path: Path) -> None:
    _repo(tmp_path)
    assert cleanup_session_sidecar(tmp_path, tmp_path / "work" / ".on-complete-M9.yaml") == []
    assert cleanup_session_sidecar(tmp_path, None) == []


def test_sidecar_outside_the_repo_is_left_alone(tmp_path: Path) -> None:
    """Raising here would abort a half-applied bookkeeping phase."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _repo(repo)
    outside = tmp_path / "elsewhere" / ".on-complete-M1.1.yaml"
    outside.parent.mkdir()
    outside.write_text("x", encoding="utf-8")
    assert cleanup_session_sidecar(repo, outside) == []
    assert outside.exists()


def test_remove_on_complete_session_is_a_plain_unlink(tmp_path: Path) -> None:
    """The on_complete tail runs after the last commit, so it must not stage."""
    _repo(tmp_path)
    path = _sidecar(tmp_path)
    _git(tmp_path, "add", "-f", "work")
    _git(tmp_path, "commit", "-m", "track sidecar")
    remove_on_complete_session(path)
    assert not path.exists()
    # Deletion is unstaged: nothing runs after this to commit it, and a staged
    # deletion would leave the index dirty for the next command.
    assert _git(tmp_path, "diff", "--cached", "--name-only").strip() == ""
