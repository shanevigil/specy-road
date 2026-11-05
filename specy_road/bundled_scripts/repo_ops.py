"""Git operations shared by the task-lifecycle entrypoints.

``do-next-available-task``, ``abort-task-pickup``, ``finish-this-task``,
``mark-implementation-reviewed``, ``pm-sync`` and ``start-milestone-session``
each grew their own copy of the same four primitives plus the integration-branch
fast-forward, reading a module-global ``ROOT``. The copies had drifted where it
shows: three spellings of the same fast-forward failure, one of which dropped
the "how do I fix this" line entirely.

These take ``repo_root`` explicitly. None of them stashes: the stash stack is
shared by every session in the checkout, so registry commits name their one
path and the clean-tree checks can ignore ``work/`` instead.

Unlike :mod:`specy_road.git_subprocess`, :func:`git_run` does **not** capture
output: ``git fetch`` and ``git push`` write progress to the terminal, and these
are the interactive commands where a user is watching for it.
"""

from __future__ import annotations

import shlex
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


#: ``work/`` holds briefs, summaries and session files that belong to whoever is
#: working; a registry commit must neither need it clean nor carry it.
_OUTSIDE_WORK = ("--", ":/", ":(exclude)work")


def working_tree_clean(repo_root: Path, *, except_work: bool = False) -> bool:
    """Whether ``git status --porcelain`` is empty (ignoring ``work/`` when asked)."""
    args = ["status", "--porcelain", *(_OUTSIDE_WORK if except_work else ())]
    return not git_checked(args, repo_root)


#: How many dirty paths a refusal lists before it summarises the rest as a count.
UNCLEAN_PATHS_SHOWN = 20


def dirty_paths(repo_root: Path, *, except_work: bool = False) -> list[str]:
    """``git status --porcelain`` lines (status, then path) the clean-tree check sees."""
    args = ["status", "--porcelain", *(_OUTSIDE_WORK if except_work else ())]
    return [line for line in git_capture(repo_root, *args).splitlines() if line.strip()]


#: The stash message the unclean-tree hint uses, so ``git stash list`` shows whose entry it is.
UNCLEAN_STASH_MESSAGE = "specy-road: unclean tree"


def unclean_tree_details(repo_root: Path, paths: list[str], *, except_work: bool = False) -> list[str]:
    """The paths that keep the tree unclean (at most 20, then a count) and how to clear them.

    The stash command runs as printed: it names this checkout and the same
    pathspec the check uses, so it sets aside exactly what was listed.
    """
    lines = [f"  {p}" for p in paths[:UNCLEAN_PATHS_SHOWN]]
    if len(paths) > UNCLEAN_PATHS_SHOWN:
        lines.append(f"  … and {len(paths) - UNCLEAN_PATHS_SHOWN} more")
    pathspec = " ".join(shlex.quote(a) for a in (_OUTSIDE_WORK if except_work else ("--", ":/")))
    stash = f"git -C {shlex.quote(str(repo_root))} stash push -u -m {shlex.quote(UNCLEAN_STASH_MESSAGE)} {pathspec}"
    lines.append(f"  Set them all aside, then retry: `{stash}`")
    lines.append("  Or commit them, or discard them (git restore for tracked edits; delete untracked files).")
    if except_work:
        lines.append("  Changes under work/ are ignored by this check.")
    return lines


def assert_working_tree_clean(repo_root: Path, detail: str = "", *, except_work: bool = False) -> None:
    """Exit 1 unless the working tree is clean, naming the paths that are not."""
    if working_tree_clean(repo_root, except_work=except_work):
        return
    print(UNCLEAN_TREE_MESSAGE, file=sys.stderr)
    if detail:
        print(f"  {detail}", file=sys.stderr)
    paths = dirty_paths(repo_root, except_work=except_work)
    for line in unclean_tree_details(repo_root, paths, except_work=except_work):
        print(line, file=sys.stderr)
    raise SystemExit(1)


def sync_integration_branch(
    repo_root: Path,
    base: str,
    remote: str,
    *,
    retry_hint: str,
    clean_tree_detail: str = "",
    except_work: bool = False,
) -> None:
    """Fetch, check out ``base``, and fast-forward it to ``remote/base``.

    ``retry_hint`` names what the user should retry, so the failure stays
    specific to the command they ran without each command re-deriving the rest
    of the message.
    """
    assert_working_tree_clean(repo_root, clean_tree_detail, except_work=except_work)
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
