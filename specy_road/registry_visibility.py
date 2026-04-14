"""Optional ``registry_visibility`` block for the PM Gantt ``/api/roadmap`` payload."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from specy_road.git_workflow_config import is_git_worktree


def registry_visibility_enabled() -> bool:
    v = os.environ.get("SPECY_ROAD_GUI_REGISTRY_VISIBILITY", "").strip().lower()
    # Unset or unknown → enabled; these values omit the block (see docs/pm-workflow.md).
    return v not in ("0", "false", "no", "off")


def count_remote_feature_rm_refs(repo_root: Path, remote: str) -> int:
    """Count local ``refs/remotes/<remote>/feature/rm-*`` (after ``git fetch``).

    Uses ``rm-*`` as one ref segment (``feature/rm-codename``), not ``feature/rm/...``.
    """
    rm = (remote or "").strip()
    if not rm or not is_git_worktree(repo_root):
        return 0
    pattern = f"refs/remotes/{rm}/feature/rm-*"
    try:
        r = subprocess.run(
            ["git", "for-each-ref", "--format=%(refname)", pattern],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return 0
    if r.returncode != 0:
        return 0
    lines = [ln.strip() for ln in (r.stdout or "").splitlines() if ln.strip()]
    return len(lines)


def build_registry_visibility(
    repo_root: Path,
    reg: dict[str, Any],
    git_workflow: dict[str, Any],
) -> dict[str, Any] | None:
    """Build ``registry_visibility`` for ``GET /api/roadmap``, or None if env-disabled.

    ``git_workflow`` must be the payload from :func:`~specy_road.git_workflow_config.build_git_workflow_status`.
    ``reg`` is parsed ``roadmap/registry.yaml`` (expects an ``entries`` list).
    """
    if not registry_visibility_enabled():
        return None
    resolved = git_workflow.get("resolved") or {}
    ib = resolved.get("integration_branch")
    rm = resolved.get("remote")
    integration_branch = ib.strip() if isinstance(ib, str) else ""
    remote = rm.strip() if isinstance(rm, str) else ""
    cur = resolved.get("git_branch_current")
    cur_s = cur.strip() if isinstance(cur, str) else ""
    on_integration_branch = bool(
        integration_branch and cur_s and cur_s == integration_branch,
    )
    entries = reg.get("entries") if isinstance(reg.get("entries"), list) else []
    local_registry_entry_count = len(entries)
    remote_feature_rm_ref_count = count_remote_feature_rm_refs(repo_root, remote)
    return {
        "on_integration_branch": on_integration_branch,
        "local_registry_entry_count": local_registry_entry_count,
        "remote_feature_rm_ref_count": remote_feature_rm_ref_count,
    }
