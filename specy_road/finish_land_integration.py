"""Merge a feature branch into the integration branch (local git, then push)."""

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

    Returns (True, "") on success, (False, message) on failure.
    """
    code, out = _git_run(repo, "fetch", remote)
    if code != 0:
        return False, f"git fetch {remote} failed: {out}"

    code, out = _git_run(repo, "checkout", integration_branch)
    if code != 0:
        return False, f"git checkout {integration_branch} failed: {out}"

    rr = f"{remote}/{integration_branch}"
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
