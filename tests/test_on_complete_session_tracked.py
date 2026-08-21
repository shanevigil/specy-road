"""Removing a tracked on-complete sidecar stages the deletion.

A bare unlink on a tracked path leaves an uncommitted deletion, and the next
checkout or sync silently restores the file — so a stale sidecar outlives the
task it belonged to.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

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


def _repo_with_tracked_sidecar(root: Path) -> Path:
    _git(root, "init")
    _git(root, "config", "user.email", "a@b.c")
    _git(root, "config", "user.name", "t")
    work = root / "work"
    work.mkdir()
    (root / "README.md").write_text("app\n", encoding="utf-8")
    path = on_complete_session_path(work, "M1.1")
    write_on_complete_session(path, node_id="M1.1", codename="cn", on_complete="merge")
    _git(root, "add", "-f", "work", "README.md")
    _git(root, "commit", "-m", "track sidecar")
    return path


def test_tracked_sidecar_removal_is_staged(tmp_path: Path) -> None:
    path = _repo_with_tracked_sidecar(tmp_path)
    remove_on_complete_session(path, tmp_path)
    assert not path.exists()
    assert _git(tmp_path, "ls-files", "work/.on-complete-M1.1.yaml").strip() == ""
    # Staged, so a checkout of the worktree cannot bring it back.
    _git(tmp_path, "checkout", "--", ".")
    assert not path.exists()


def test_untracked_sidecar_is_just_unlinked(tmp_path: Path) -> None:
    work = tmp_path / "work"
    work.mkdir()
    path = on_complete_session_path(work, "M1.1")
    write_on_complete_session(path, node_id="M1.1", codename="cn", on_complete="pr")
    remove_on_complete_session(path, tmp_path)
    assert not path.exists()


def test_missing_sidecar_is_a_no_op(tmp_path: Path) -> None:
    remove_on_complete_session(tmp_path / "work" / ".on-complete-M9.yaml", tmp_path)
