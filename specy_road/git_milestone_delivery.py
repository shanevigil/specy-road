"""Detect whether a milestone rollup branch is merged into the integration branch (remote tips)."""

from __future__ import annotations

import subprocess
from pathlib import Path


def _run(repo: Path, *args: str) -> tuple[int, str]:
    r = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    return r.returncode, (r.stdout or r.stderr or "").strip()


def resolve_remote_tip_sha(repo: Path, remote: str, branch: str) -> str | None:
    """Return SHA of ``remote/branch`` if the ref exists locally."""
    code, out = _run(repo, "rev-parse", f"{remote}/{branch}")
    if code != 0 or not out:
        return None
    return out.splitlines()[0].strip()


def rollup_merged_into_integration(
    repo: Path,
    *,
    remote: str,
    rollup_branch: str,
    integration_branch: str,
) -> bool | None:
    """
    True if ``rollup_branch`` tip is an ancestor of ``integration_branch`` tip.

    None if either remote-tracking ref is missing (caller should fetch or use fallback).
    """
    rb = resolve_remote_tip_sha(repo, remote, rollup_branch)
    ib = resolve_remote_tip_sha(repo, remote, integration_branch)
    if not rb or not ib:
        return None
    code, _ = _run(repo, "merge-base", "--is-ancestor", rb, ib)
    return code == 0
