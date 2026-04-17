"""Stash/restore work/ changes around the integration-branch registry commit (F-011).

Used by both ``do-next-available-task`` and ``mark-implementation-reviewed``
so registry mutations on the integration branch never carry uncommitted
work/ changes (briefs, summaries, etc.).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def stash_work_dir_changes(repo_root: Path, scope_label: str) -> bool:
    """Stash work/ changes if any. Returns True if a stash was created.

    Robust against non-git directories (used by tests with tmp_path repos).
    """
    r = subprocess.run(
        ["git", "status", "--porcelain", "--", "work"],
        cwd=repo_root, capture_output=True, text=True, check=False,
    )
    if r.returncode != 0 or not (r.stdout or "").strip():
        return False
    rs = subprocess.run(
        [
            "git", "stash", "push", "--include-untracked",
            "-m", f"specy-road: temp stash work/ around {scope_label}",
            "--", "work",
        ],
        cwd=repo_root, capture_output=True, text=True, check=False,
    )
    return rs.returncode == 0


def restore_work_dir_changes(repo_root: Path, stashed: bool) -> None:
    if not stashed:
        return
    r = subprocess.run(
        ["git", "stash", "pop"], cwd=repo_root,
        capture_output=True, text=True, check=False,
    )
    if r.returncode != 0:
        print(
            "warning: could not auto-restore your work/ changes; run "
            "`git stash list` and `git stash pop` manually "
            f"({(r.stderr or r.stdout or '').strip()}).",
            file=sys.stderr,
        )
