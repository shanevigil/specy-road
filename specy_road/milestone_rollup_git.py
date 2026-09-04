"""Git steps for milestone rollup: bookkeeping onto integration, full merge into rollup branch."""

from __future__ import annotations

from pathlib import Path

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

    code, out = git_code(["cherry-pick", bookkeeping_commit], repo)
    if code != 0:
        git_code(["cherry-pick", "--abort"], repo)
        git_code(["checkout", leaf_branch], repo)
        return (
            False,
            f"cherry-pick {bookkeeping_commit[:8]} onto {integration_branch} failed "
            f"(resolve conflicts on {integration_branch}, then continue): {out}",
        )

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
