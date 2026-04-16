"""PM GUI: integration-branch registry fingerprint and auto-FF status.

See :mod:`specy_road.registry_remote_overlay` for merge + fetch orchestration.
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Any

from specy_road.git_workflow_config import (
    current_branch_name,
    is_git_worktree,
    resolve_integration_defaults,
    working_tree_clean,
)

REGISTRY_REL = Path("roadmap") / "registry.yaml"


def _git_ok(
    args: list[str], cwd: Path, timeout: float
) -> tuple[bool, str]:
    try:
        r = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False, ""
    if r.returncode != 0:
        return False, (r.stderr or r.stdout or "").strip()
    return True, (r.stdout or "").strip()


def describe_integration_branch_auto_ff(
    repo_root: Path,
) -> dict[str, Any] | None:
    """When integration auto-FF is enabled, report skip reason or sync vs remote."""
    from specy_road.registry_remote_overlay import integration_branch_auto_ff_enabled

    if not integration_branch_auto_ff_enabled(repo_root):
        return {"enabled": False}
    if not is_git_worktree(repo_root):
        base0, remote0, _ = resolve_integration_defaults(
            repo_root,
            explicit_base=None,
            explicit_remote=None,
        )
        r0 = (remote0 or "").strip() or "origin"
        return {
            "enabled": True,
            "skipped_reason": "not_git_repo",
            "integration_branch": base0,
            "remote": r0,
        }
    base, remote, _warns = resolve_integration_defaults(
        repo_root,
        explicit_base=None,
        explicit_remote=None,
    )
    rname = (remote or "").strip() or "origin"
    ib_ref = f"refs/remotes/{rname}/{base}"
    out: dict[str, Any] = {
        "enabled": True,
        "integration_branch": base,
        "remote": rname,
    }
    cur = current_branch_name(repo_root)
    if not cur or cur != base:
        out["skipped_reason"] = "not_on_integration_branch"
        return out
    if not working_tree_clean(repo_root):
        out["skipped_reason"] = "dirty_working_tree"
        return out
    ok_tip, tip_sha = _git_ok(["rev-parse", ib_ref], repo_root, 15.0)
    ok_head, head_sha = _git_ok(["rev-parse", "HEAD"], repo_root, 15.0)
    if not ok_tip or not (tip_sha or "").strip():
        out["skipped_reason"] = "integration_ref_unavailable"
        return out
    if not ok_head or not (head_sha or "").strip():
        out["skipped_reason"] = "integration_ref_unavailable"
        return out
    if head_sha.strip() == tip_sha.strip():
        out["sync_state"] = "up_to_date"
        return out
    ok_a, _ = _git_ok(
        ["merge-base", "--is-ancestor", "HEAD", ib_ref],
        repo_root,
        15.0,
    )
    ok_b, _ = _git_ok(
        ["merge-base", "--is-ancestor", ib_ref, "HEAD"],
        repo_root,
        15.0,
    )
    if ok_a:
        out["sync_state"] = "behind_ff_possible"
    elif ok_b:
        out["sync_state"] = "ahead_of_remote"
    else:
        out["sync_state"] = "diverged"
    return out


def remote_registry_overlay_fingerprint_addendum(repo_root: Path) -> int:
    """Hash addendum: remote feature refs + integration-branch registry blob."""
    from specy_road.registry_remote_overlay import (
        registry_remote_overlay_enabled,
        resolve_git_remote,
    )

    if not registry_remote_overlay_enabled(repo_root):
        return 0
    if not is_git_worktree(repo_root):
        return 0
    rm = resolve_git_remote(repo_root)
    base, _, _ = resolve_integration_defaults(
        repo_root,
        explicit_base=None,
        explicit_remote=None,
    )
    ib_ref = f"refs/remotes/{rm}/{base}"
    chunks: list[str] = []
    pattern = f"refs/remotes/{rm}/feature/rm-*"
    ok, feat_out = _git_ok(
        ["for-each-ref", "--format=%(objectname) %(refname)", pattern],
        repo_root,
        60.0,
    )
    if ok and feat_out.strip():
        chunks.append(feat_out.strip())
    ok_ib, _ = _git_ok(["show-ref", "--verify", ib_ref], repo_root, 15.0)
    if ok_ib:
        ok_blob, blob_rev = _git_ok(
            ["rev-parse", f"{ib_ref}:{REGISTRY_REL.as_posix()}"],
            repo_root,
            15.0,
        )
        if ok_blob and (blob_rev or "").strip():
            chunks.append(f"iblob:{blob_rev.strip()}")
        else:
            ok_tip, tip = _git_ok(["rev-parse", ib_ref], repo_root, 15.0)
            if ok_tip and (tip or "").strip():
                chunks.append(f"itip:{tip.strip()}")
    if not chunks:
        return 0
    h = hashlib.sha256("\n".join(chunks).encode("utf-8")).digest()[:8]
    return int.from_bytes(h, "little")
