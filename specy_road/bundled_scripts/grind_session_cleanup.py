"""End-of-session tidy-up for ``specy-road grind-session``.

``finish-this-task`` pushes the feature branch and, in merge mode, deliberately
checks it back out — a standalone dev wants to stay where they were working. A
grind session is different: nobody is standing there, the branch is merged, and
the loop used to end on the last ``feature/rm-*`` with every earlier one still
present locally and on the remote.

So the loop returns to the integration branch when it finishes cleanly, and
deletes the branches it finished only when asked. Nothing here can change the
session's exit code: a session that did the work has succeeded even if the tidy-up
could not run.
"""

from __future__ import annotations

from pathlib import Path

from specy_road.bundled_scripts.grind_session_events import EventEmitter
from specy_road.git_subprocess import git_code
from specy_road.git_workflow_config import resolve_integration_defaults


def merged_into(repo_root: Path, branch: str, base: str) -> bool:
    """Whether ``base`` already contains ``branch``.

    Load-bearing before any deletion. ``finish --push`` gives the branch an
    upstream, so ``git branch -d`` only checks merged-into-upstream and would
    happily delete a branch that never reached the integration branch — which
    is exactly what ``auto`` mode leaves behind when it falls back to a PR.
    """
    code, _out = git_code(["merge-base", "--is-ancestor", branch, base], repo_root)
    return code == 0


def delete_local_branch(repo_root: Path, branch: str, base: str) -> dict | None:
    """``git branch -d`` once ``base`` contains ``branch``. Returns the failure, or ``None``."""
    if not merged_into(repo_root, branch, base):
        return {
            "branch": branch,
            "step": "merge_base",
            "message": f"not merged into {base}; left alone",
        }
    code, out = git_code(["branch", "-d", branch], repo_root)
    if code != 0:
        return {"branch": branch, "step": "branch_d", "message": out}
    return None


def delete_remote_branch(
    repo_root: Path, branch: str, base: str, remote: str
) -> dict | None:
    """Delete ``remote/branch`` only while it is still the tip ``base`` contains.

    The delete is leased to that tip (``--force-with-lease=<ref>:<sha>``), so a
    push that lands after the check is refused and the branch stays. Returns
    the failure, or ``None``.
    """
    # The local check says our copy is merged; it says nothing about theirs.
    # Someone else pushing to the same feature branch after our merge would
    # lose that commit, and a deleted remote branch is not recoverable here.
    tracking = f"{remote}/{branch}"
    if not merged_into(repo_root, tracking, base):
        return {
            "branch": branch,
            "step": "push_delete",
            "message": (
                f"{tracking} is not contained in {base} (or is unknown here); "
                "left on the remote. Delete it yourself once you have checked it."
            ),
        }
    code, sha = git_code(["rev-parse", tracking], repo_root)
    if code != 0 or not sha:
        return {
            "branch": branch,
            "step": "push_delete",
            "message": f"could not read {tracking}; left on the remote",
        }
    code, out = git_code(
        ["push", remote, f"--force-with-lease=refs/heads/{branch}:{sha}", "--delete", branch],
        repo_root,
    )
    if code != 0:
        return {
            "branch": branch,
            "step": "push_delete",
            "message": f"{tracking} at {sha} was not deleted; left on the remote. {out}",
        }
    return None


def delete_merged_branch(
    repo_root: Path, branch: str, base: str, remote: str, *, push: bool
) -> tuple[bool, bool, dict | None]:
    """Delete one merged branch, the remote copy only after the local one. Returns (local_ok, remote_ok, failure)."""
    failure = delete_local_branch(repo_root, branch, base)
    if failure is not None:
        return False, False, failure
    if not push:
        return True, False, None
    failure = delete_remote_branch(repo_root, branch, base, remote)
    return True, failure is None, failure


def _hint(branches: list[str], remote: str, *, push: bool) -> str:
    local = "git branch -d " + " ".join(branches)
    if not push:
        return local
    return f"{local} && git push {remote} --delete " + " ".join(branches)


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
        for branch in ordered:
            local_ok, remote_ok, failure = delete_merged_branch(
                repo_root, branch, base, remote, push=bool(args.push)
            )
            if local_ok:
                deleted_local.append(branch)
            if remote_ok:
                deleted_remote.append(branch)
            if failure:
                failed.append(failure)

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
