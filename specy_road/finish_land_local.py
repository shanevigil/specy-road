"""Root ``land: push | local`` for finish-this-task's merge (and auto) mode (M15.22).

M14.4.1 gave each ``nested_repos`` entry ``land``; the top-level ``land`` key in
``roadmap/git-workflow.yaml`` gives the root repository the same choice.
``push`` (the default) is the landing finish always did
(:func:`specy_road.finish_land_integration.land_merge_feature_into_integration`).
``local`` merges the leaf's branch into the **local** integration branch the same
way -- nested repositories first, bookkeeping conflicts resolved
deterministically, the land check on the merge commit -- and stops there:
nothing is fetched or pushed, and finish says so.
"""

from __future__ import annotations

from pathlib import Path

from specy_road.finish_land_check import resolve_land_check_cmd, run_land_check
from specy_road.finish_land_deterministic import merge_feature_deterministically
from specy_road.finish_land_integration import (
    _checkout_feature_after_landing,
    _reset_integration,
    holder_project_root,
    integration_worktree,
    integration_worktree_problem,
    land_merge_feature_into_integration,
    print_merge_push_notice,
    tracking_ref_snapshot,
)
from specy_road.git_subprocess import git_code, git_ok
from specy_road.nested_repos import land_nested_branches
from specy_road.workflow_prefs import LAND_LOCAL, root_land


def _merge_here(tree: Path, ib: str, feature_branch: str, check: str | None) -> tuple[bool, str]:
    """Merge into ``ib`` (checked out in ``tree``) and land-check it; a failed check puts ``ib`` back."""
    _ok, pre = git_ok(["rev-parse", "HEAD"], tree)
    ok, out = merge_feature_deterministically(tree, integration_branch=ib, feature_branch=feature_branch)
    if not ok:
        return False, out
    problem = run_land_check(tree, check) if check else None
    if problem is not None:
        return False, f"{problem}\n  {_reset_integration(tree, ib, pre)}"
    return True, ""


def land_root_locally(
    repo: Path, *, integration_branch: str, feature_branch: str, land_check_cmd: str | None = None,
) -> tuple[bool, str]:
    """``land: local``: merge ``feature_branch`` into the local ``integration_branch``; nothing fetched or pushed.

    Where another worktree holds the integration branch the merge runs there,
    only while it is clean, as the push landing does. ``(True, "")`` when the
    checkout worked, ``(True, warning)`` when only the final checkout of the
    feature branch failed, or ``(False, why)``. A branch already merged (a
    re-run) merges nothing.
    """
    ib = integration_branch
    if not git_ok(["rev-parse", "--verify", "--quiet", f"refs/heads/{ib}"], repo)[0]:
        return False, f"no local {ib} to merge into (land: local); create it, then re-run"
    problem = integration_worktree_problem(repo, ib)
    if problem is not None:
        return False, problem
    ok, err = land_nested_branches(repo, feature_branch)
    if not ok:
        return False, err
    check = resolve_land_check_cmd(repo, cli=land_check_cmd)
    holder = integration_worktree(repo, ib)
    if holder is not None:
        return _merge_here(holder_project_root(repo, holder), ib, feature_branch, check)
    code, out = git_code(["checkout", ib], repo)
    if code != 0:
        return False, f"git checkout {ib} failed: {out}"
    ok, err = _merge_here(repo, ib, feature_branch, check)
    return _checkout_feature_after_landing(repo, feature_branch, ok, err)


def land_on_integration(
    repo: Path, *, remote: str, ib: str, branch: str, land_check_cmd: str | None,
    tracking_before: str | None = None,
) -> tuple[bool, str, str]:
    """Land ``branch`` on ``ib`` per the root ``land``: ``(ok, error or warning, what was done)``.

    The second value is a warning when the landing succeeded and only the final
    ``git checkout`` of the feature branch failed. Each step is announced first.

    ``tracking_before`` is :func:`tracking_ref_snapshot` taken before the
    caller's own fetch; ``None`` takes it here (push only).
    """
    if root_land(repo) == LAND_LOCAL:
        print(f"\nMerge mode will merge {branch!r} into local {ib!r} (land: local): nothing is fetched or pushed.")
        ok, err = land_root_locally(repo, integration_branch=ib, feature_branch=branch,
                                    land_check_cmd=land_check_cmd)
        return ok, err, f"merged {branch} into local {ib} (land: local); nothing pushed to {remote}"
    if tracking_before is None:
        tracking_before = tracking_ref_snapshot(repo, remote=remote, integration_branch=ib)
    print_merge_push_notice(repo, remote=remote, integration_branch=ib, feature_branch=branch)
    ok, err = land_merge_feature_into_integration(
        repo, remote=remote, integration_branch=ib, feature_branch=branch,
        land_check_cmd=land_check_cmd, tracking_before=tracking_before,
    )
    return ok, err, f"merged {branch} into {ib} and pushed to {remote}"
