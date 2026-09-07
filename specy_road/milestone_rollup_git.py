"""Git steps for milestone rollup: bookkeeping onto integration, full merge into rollup branch."""

from __future__ import annotations

from pathlib import Path

from specy_road.finish_land_deterministic import (
    DETERMINISTIC_PATHS,
    DeterministicResolveError,
    codename_from_branch,
    reconcile_or_rollback,
    resolve_deterministic_paths,
    unmerged_paths,
)
from specy_road.git_subprocess import git_checked, git_code


def current_branch(repo: Path) -> str:
    return git_checked(["rev-parse", "--abbrev-ref", "HEAD"], repo)


def rev_parse_head(repo: Path) -> str:
    return git_checked(["rev-parse", "HEAD"], repo)


def branch_exists(repo: Path, branch: str) -> bool:
    code, _ = git_code(["rev-parse", "--verify", branch], repo)
    return code == 0


def push_branch(repo: Path, remote: str, branch: str) -> tuple[bool, str]:
    code, out = git_code(["push", "-u", remote, branch], repo)
    if code != 0:
        return False, out or "git push failed"
    return True, ""


def _nothing_staged(repo: Path) -> bool:
    """Whether the index matches HEAD, i.e. there is no commit to make."""
    code, _ = git_code(["diff", "--cached", "--quiet"], repo)
    return code == 0


def _undo_staged_pick(repo: Path, pre_sha: str) -> None:
    """Clean up after a ``cherry-pick --no-commit``.

    ``cherry-pick --abort`` is not available here: with ``--no-commit`` git
    never starts a sequencer, so abort fails with "no cherry-pick or revert in
    progress" and leaves the conflicted paths in the worktree. Resetting to the
    commit we started from is the only cleanup that works, and it is safe
    because nothing has been pushed.
    """
    git_code(["reset", "--hard", pre_sha], repo)


def _cherry_pick_deterministically(
    repo: Path,
    *,
    integration_branch: str,
    bookkeeping_commit: str,
    leaf_branch: str,
) -> tuple[bool, str]:
    """Cherry-pick a leaf's bookkeeping commit onto the integration branch.

    The milestone rollup lands bookkeeping this way instead of merging, but a
    cherry-pick is a 3-way merge too, over exactly the same three files and
    with exactly the same exposure. Resolution is therefore identical; only the
    ref standing in for "the other side" differs.

    Returns ``(True, "")``, or ``(False, message)`` with the cherry-pick
    aborted. The caller checks the leaf branch back out.
    """
    codename = codename_from_branch(leaf_branch)
    short = bookkeeping_commit[:8]
    pre_sha = rev_parse_head(repo)

    code, out = git_code(["cherry-pick", "--no-commit", bookkeeping_commit], repo)
    if code != 0:
        unmerged = unmerged_paths(repo)
        stray = [p for p in unmerged if p not in DETERMINISTIC_PATHS]
        if not unmerged or stray:
            _undo_staged_pick(repo, pre_sha)
            return (
                False,
                f"cherry-pick {short} onto {integration_branch} failed "
                f"(resolve conflicts on {integration_branch}, then continue): {out}",
            )
        print(
            "[ok] resolving generated bookkeeping conflict in "
            f"{', '.join(unmerged)} from {integration_branch}"
        )

    try:
        staged = resolve_deterministic_paths(
            repo, codename=codename, other_ref=bookkeeping_commit
        )
    except DeterministicResolveError as exc:
        _undo_staged_pick(repo, pre_sha)
        return False, f"cherry-pick {short} onto {integration_branch} failed: {exc}"

    if staged:
        code, out = git_code(["add", "--", *staged], repo)
        if code != 0:
            _undo_staged_pick(repo, pre_sha)
            return (
                False,
                f"cherry-pick {short} onto {integration_branch} failed while "
                f"staging {', '.join(staged)}: {out}",
            )

    if _nothing_staged(repo):
        # The bookkeeping is already on the integration branch and resolution
        # changed nothing. Committing would make an empty commit.
        _undo_staged_pick(repo, pre_sha)
        return True, ""

    code, out = git_code(["commit", "-C", bookkeeping_commit, "--no-edit"], repo)
    if code != 0:
        _undo_staged_pick(repo, pre_sha)
        return (
            False,
            f"cherry-pick {short} onto {integration_branch} failed to commit: {out}",
        )
    problem = reconcile_or_rollback(repo, pre_sha)
    if problem is not None:
        return False, f"cherry-pick {short} onto {integration_branch} failed: {problem}"
    return True, ""


def cherry_pick_bookkeeping_to_integration(
    repo: Path,
    *,
    remote: str,
    integration_branch: str,
    bookkeeping_commit: str,
    leaf_branch: str,
) -> tuple[bool, str]:
    """
    Move to integration, fast-forward from remote, cherry-pick bookkeeping commit, push.
    Ends on ``integration_branch``.
    """
    code, out = git_code(["fetch", remote], repo)
    if code != 0:
        return False, f"git fetch {remote} failed: {out}"

    code, out = git_code(["checkout", integration_branch], repo)
    if code != 0:
        git_code(["checkout", leaf_branch], repo)
        return False, f"git checkout {integration_branch} failed: {out}"

    rr = f"{remote}/{integration_branch}"
    code, out = git_code(["merge", "--ff-only", rr], repo)
    if code != 0:
        git_code(["checkout", leaf_branch], repo)
        return (
            False,
            f"fast-forward {integration_branch} to {rr} failed: {out}",
        )

    ok, out = _cherry_pick_deterministically(
        repo,
        integration_branch=integration_branch,
        bookkeeping_commit=bookkeeping_commit,
        leaf_branch=leaf_branch,
    )
    if not ok:
        git_code(["checkout", leaf_branch], repo)
        return False, out

    code, out = git_code(["push", remote, integration_branch], repo)
    if code != 0:
        git_code(["checkout", leaf_branch], repo)
        return False, f"git push {remote} {integration_branch} failed: {out}"

    return True, ""


def merge_leaf_into_rollup(
    repo: Path,
    *,
    remote: str,
    rollup_branch: str,
    leaf_branch: str,
    integration_branch: str,
) -> tuple[bool, str]:
    """
    Check out rollup, merge leaf, push rollup. Ends on ``integration_branch``.
    """
    code, out = git_code(["fetch", remote], repo)
    if code != 0:
        return False, f"git fetch {remote} failed: {out}"

    code, out = git_code(["checkout", rollup_branch], repo)
    if code != 0:
        return False, f"git checkout {rollup_branch} failed: {out}"

    code, out = git_code(["merge", "--no-edit", leaf_branch], repo)
    if code != 0:
        git_code(["merge", "--abort"], repo)
        git_code(["checkout", integration_branch], repo)
        return False, f"git merge {leaf_branch} into {rollup_branch} failed: {out}"

    code, out = git_code(["push", remote, rollup_branch], repo)
    if code != 0:
        git_code(["checkout", integration_branch], repo)
        return False, f"git push {remote} {rollup_branch} failed: {out}"

    code, out = git_code(["checkout", integration_branch], repo)
    if code != 0:
        return False, f"git checkout {integration_branch} after rollup merge failed: {out}"

    return True, ""
