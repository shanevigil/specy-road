"""End-of-session tidy-up for ``specy-road grind-session``.

``finish-this-task`` pushes the feature branch and, in merge mode, deliberately
checks it back out — a standalone dev wants to stay where they were working. A
grind session is different: nobody is standing there, the branch is merged, and
the loop used to end on the last ``feature/rm-*`` with every earlier one still
present locally and on the remote.

So the loop returns to the integration branch when it finishes cleanly, and
deletes the branches it finished only when asked (``--delete-merged-branches``,
a deprecated alias of ``doctor --prune --kind branches``). A branch the cleanup
planner's live rule holds (an open claim or rollup, a running worker, a live
session: :func:`specy_road.cleanup_plan.held_branches`) is left. Nothing here can
change the session's exit code: a session that did the work has succeeded even if
the tidy-up could not run.
"""

from __future__ import annotations

from pathlib import Path

from specy_road.bundled_scripts.grind_session_events import EventEmitter
from specy_road.cleanup_plan import held_branches
from specy_road.git_subprocess import git_code
from specy_road.git_workflow_config import resolve_integration_defaults
from specy_road.merged_branch import delete_merged_branch


def _hint(branches: list[str], remote: str, *, push: bool) -> str:
    local = "git branch -d " + " ".join(branches)
    if not push:
        return local
    return f"{local} && git push {remote} --delete " + " ".join(branches)


def _delete_finished(repo_root: Path, branches: list[str], base: str, remote: str, *, push: bool
                     ) -> tuple[list[str], list[str], list[dict]]:
    """Delete each merged branch the live rule does not hold.

    Returns (deleted local, deleted remote, failed).
    """
    held, _paths = held_branches(repo_root, base)
    deleted_local: list[str] = []
    deleted_remote: list[str] = []
    failed: list[dict] = []
    for branch in branches:
        if branch in held:
            failed.append({"branch": branch, "step": "live", "message": held[branch][1]})
            continue
        local_ok, remote_ok, failure = delete_merged_branch(
            repo_root, branch, base, remote, push=push)
        if local_ok:
            deleted_local.append(branch)
        if remote_ok:
            deleted_remote.append(branch)
        if failure:
            failed.append(failure)
    return deleted_local, deleted_remote, failed


def run_session_cleanup(
    args, repo_root: Path, emitter: EventEmitter, branches: list[str]
) -> None:
    """Return to the integration branch, and optionally drop merged branches."""
    ordered = list(dict.fromkeys(b for b in branches if b))
    base, remote, warnings = resolve_integration_defaults(
        repo_root, explicit_base=args.base, explicit_remote=args.remote
    )
    failed: list[dict] = []
    code, out = git_code(["checkout", base], repo_root)
    checked_out = code == 0
    if not checked_out:
        failed.append({"branch": base, "step": "checkout", "message": out})

    deleted_local: list[str] = []
    deleted_remote: list[str] = []
    wanted = bool(getattr(args, "delete_merged_branches", False))
    if wanted and checked_out:
        deleted_local, deleted_remote, refused = _delete_finished(
            repo_root, ordered, base, remote, push=bool(args.push))
        failed += refused

    emitter.emit(
        "cleanup",
        integration_branch=base,
        remote=remote,
        checked_out=checked_out,
        deleted_local=deleted_local,
        deleted_remote=deleted_remote,
        failed=failed,
        warnings=warnings,
        hint=None if wanted else _hint(ordered, remote, push=bool(args.push)),
    )
