"""Git operations shared by the task-lifecycle entrypoints.

``do-next-available-task``, ``abort-task-pickup``, ``finish-this-task``,
``mark-implementation-reviewed``, ``pm-sync`` and ``start-milestone-session``
each grew their own copy of the same four primitives plus the integration-branch
fast-forward, reading a module-global ``ROOT``. The copies had drifted where it
shows: three spellings of the same fast-forward failure, one of which dropped
the "how do I fix this" line entirely.

These take ``repo_root`` explicitly, following ``work_dir_stash`` -- the helper
that was already factored out of two of these scripts for the same reason.

Unlike :mod:`specy_road.git_subprocess`, :func:`git_run` does **not** capture
output: ``git fetch`` and ``git push`` write progress to the terminal, and these
are the interactive commands where a user is watching for it.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from specy_road.git_subprocess import git_checked

UNCLEAN_TREE_MESSAGE = (
    "error: working tree is not clean (commit, stash, or discard changes first)."
)


def git_run(repo_root: Path, *args: str) -> None:
    """Run git with output passed through. Raises ``CalledProcessError``."""
    subprocess.check_call(["git", *args], cwd=repo_root)


def git_capture(repo_root: Path, *args: str) -> str:
    """Raw stdout. Raises ``CalledProcessError`` on a non-zero exit."""
    return subprocess.run(
        ["git", *args], cwd=repo_root, capture_output=True, text=True, check=True
    ).stdout


def current_branch(repo_root: Path) -> str:
    """The checked-out branch name."""
    return git_checked(["rev-parse", "--abbrev-ref", "HEAD"], repo_root)


def working_tree_clean(repo_root: Path) -> bool:
    """Whether ``git status --porcelain`` is empty."""
    return not git_checked(["status", "--porcelain"], repo_root)


def assert_working_tree_clean(repo_root: Path, detail: str = "") -> None:
    """Exit 1 unless the working tree is clean."""
    if working_tree_clean(repo_root):
        return
    print(UNCLEAN_TREE_MESSAGE, file=sys.stderr)
    if detail:
        print(f"  {detail}", file=sys.stderr)
    raise SystemExit(1)


def sync_integration_branch(
    repo_root: Path,
    base: str,
    remote: str,
    *,
    retry_hint: str,
    clean_tree_detail: str = "",
) -> None:
    """Fetch, check out ``base``, and fast-forward it to ``remote/base``.

    ``retry_hint`` names what the user should retry, so the failure stays
    specific to the command they ran without each command re-deriving the rest
    of the message.
    """
    assert_working_tree_clean(repo_root, clean_tree_detail)
    git_run(repo_root, "fetch", remote)
    git_run(repo_root, "checkout", base)
    try:
        git_run(repo_root, "merge", "--ff-only", f"{remote}/{base}")
    except subprocess.CalledProcessError:
        print(
            f"error: could not fast-forward local '{base}' to {remote}/{base}.",
            file=sys.stderr,
        )
        print(
            "  Resolve your local integration branch (e.g. pull with rebase, or "
            f"reset after team agreement), then {retry_hint}.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
