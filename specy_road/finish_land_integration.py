"""Merge a feature branch into the integration branch (local git, then push).

F-012: ``--on-complete merge`` previously fell through to the PR-instructions
tail when ``git checkout <integration_branch>`` failed (e.g. the configured
integration_branch did not exist locally). This module now validates the
integration branch ref **before** any state-changing git operations and
returns a structured error so the caller can surface a hard failure instead
of misleading PR instructions.
"""

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


def _ref_exists_local(repo: Path, ref: str) -> bool:
    code, _ = _git_run(repo, "rev-parse", "--verify", ref)
    return code == 0


def _integration_branch_present(
    repo: Path, remote: str, integration_branch: str
) -> tuple[bool, str]:
    """Return (ok, where) — either ``refs/heads/<branch>`` or remote-tracking ref."""
    if _ref_exists_local(repo, f"refs/heads/{integration_branch}"):
        return True, f"refs/heads/{integration_branch}"
    if _ref_exists_local(repo, f"refs/remotes/{remote}/{integration_branch}"):
        return True, f"refs/remotes/{remote}/{integration_branch}"
    return False, ""


def land_merge_feature_into_integration(
    repo: Path,
    *,
    remote: str,
    integration_branch: str,
    feature_branch: str,
) -> tuple[bool, str]:
    """
    Fetch, checkout integration, fast-forward to remote tracking ref, merge feature,
    push integration, checkout feature.

    Returns (True, "") on success, (False, message) on failure. Failure
    messages are structured so callers can surface a hard error rather than
    silently falling back to PR instructions (F-012).
    """
    code, out = _git_run(repo, "fetch", remote)
    if code != 0:
        return False, f"git fetch {remote} failed: {out}"

    # F-012: verify integration_branch actually exists locally OR remotely
    # BEFORE doing anything destructive. If the user's git-workflow.yaml
    # points at a branch name that doesn't exist (e.g. 'main' on a 'master'
    # repo), bail with a clear error rather than confusing checkout output.
    ok, _ref = _integration_branch_present(repo, remote, integration_branch)
    if not ok:
        return (
            False,
            f"integration branch {integration_branch!r} does not exist "
            f"locally or on {remote!r}. Check roadmap/git-workflow.yaml: "
            "the integration_branch must match a real branch in your repo. "
            f"To create it locally from {remote}, run: "
            f"git fetch {remote} && git branch {integration_branch} "
            f"{remote}/{integration_branch}",
        )

    code, out = _git_run(repo, "checkout", integration_branch)
    if code != 0:
        return False, f"git checkout {integration_branch} failed: {out}"

    rr = f"{remote}/{integration_branch}"
    if _ref_exists_local(repo, f"refs/remotes/{rr}"):
        code, out = _git_run(repo, "merge", "--ff-only", rr)
        if code != 0:
            _git_run(repo, "checkout", feature_branch)
            return (
                False,
                f"fast-forward {integration_branch} to {rr} failed "
                f"(sync the integration branch locally, then retry): {out}",
            )

    code, out = _git_run(repo, "merge", "--no-edit", feature_branch)
    if code != 0:
        _git_run(repo, "merge", "--abort")
        _git_run(repo, "checkout", feature_branch)
        return False, f"git merge {feature_branch} into {integration_branch} failed: {out}"

    code, out = _git_run(repo, "push", remote, integration_branch)
    if code != 0:
        _git_run(repo, "checkout", feature_branch)
        return (
            False,
            f"git push {remote} {integration_branch} failed (local merge may exist): {out}",
        )

    code, out = _git_run(repo, "checkout", feature_branch)
    if code != 0:
        return False, f"git checkout {feature_branch} after merge failed: {out}"
    return True, ""
