"""Git steps for milestone rollup: bookkeeping onto integration, full merge into rollup branch."""

from __future__ import annotations

import subprocess
from pathlib import Path


def _git_run(repo: Path, *args: str) -> tuple[int, str]:
    r = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    err = (r.stderr or r.stdout or "").strip()
    return r.returncode, err


def current_branch(repo: Path) -> str:
    r = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    return r.stdout.strip()


def rev_parse_head(repo: Path) -> str:
    r = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    return r.stdout.strip()


def branch_exists(repo: Path, branch: str) -> bool:
    code, _ = _git_run(repo, "rev-parse", "--verify", branch)
    return code == 0


def push_branch(repo: Path, remote: str, branch: str) -> tuple[bool, str]:
    code, out = _git_run(repo, "push", "-u", remote, branch)
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
    code, out = _git_run(repo, "fetch", remote)
    if code != 0:
        return False, f"git fetch {remote} failed: {out}"

    code, out = _git_run(repo, "checkout", integration_branch)
    if code != 0:
        _git_run(repo, "checkout", leaf_branch)
        return False, f"git checkout {integration_branch} failed: {out}"

    rr = f"{remote}/{integration_branch}"
    code, out = _git_run(repo, "merge", "--ff-only", rr)
    if code != 0:
        _git_run(repo, "checkout", leaf_branch)
        return (
            False,
            f"fast-forward {integration_branch} to {rr} failed: {out}",
        )

    code, out = _git_run(repo, "cherry-pick", bookkeeping_commit)
    if code != 0:
        _git_run(repo, "cherry-pick", "--abort")
        _git_run(repo, "checkout", leaf_branch)
        return (
            False,
            f"cherry-pick {bookkeeping_commit[:8]} onto {integration_branch} failed "
            f"(resolve conflicts on {integration_branch}, then continue): {out}",
        )

    code, out = _git_run(repo, "push", remote, integration_branch)
    if code != 0:
        _git_run(repo, "checkout", leaf_branch)
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
    code, out = _git_run(repo, "fetch", remote)
    if code != 0:
        return False, f"git fetch {remote} failed: {out}"

    code, out = _git_run(repo, "checkout", rollup_branch)
    if code != 0:
        return False, f"git checkout {rollup_branch} failed: {out}"

    code, out = _git_run(repo, "merge", "--no-edit", leaf_branch)
    if code != 0:
        _git_run(repo, "merge", "--abort")
        _git_run(repo, "checkout", integration_branch)
        return False, f"git merge {leaf_branch} into {rollup_branch} failed: {out}"

    code, out = _git_run(repo, "push", remote, rollup_branch)
    if code != 0:
        _git_run(repo, "checkout", integration_branch)
        return False, f"git push {remote} {rollup_branch} failed: {out}"

    code, out = _git_run(repo, "checkout", integration_branch)
    if code != 0:
        return False, f"git checkout {integration_branch} after rollup merge failed: {out}"

    return True, ""
