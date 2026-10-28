"""Merge a feature branch into the integration branch (local git, then push).

F-012: ``--on-complete merge`` previously fell through to the PR-instructions
tail when ``git checkout <integration_branch>`` failed (e.g. the configured
integration_branch did not exist locally). This module now validates the
integration branch ref **before** any state-changing git operations and
returns a structured error so the caller can surface a hard failure instead
of misleading PR instructions.

Registry and generated files are resolved, not merged. ``roadmap/registry.yaml``
is a keyed collection and ``roadmap.md`` / ``roadmap-context.md`` are generated
in full, so a line-based 3-way merge of any of them can conflict -- leaving a
finish half-done -- or succeed while keeping a claim row both lanes removed. The
merge is therefore staged, those three paths are recomputed from the integration
branch plus the merged graph, and only then is the merge commit created. See
:mod:`specy_road.finish_land_deterministic`.

When the integration branch is checked out in another worktree (``worker
delegate``'s layout: the coordinator's checkout on ``main``, the leaf in
``work/.worktrees/<codename>``), ``git checkout`` of it here is impossible, so
the merge runs in that worktree instead -- only when it has no uncommitted
changes to tracked files, so another checkout's work is never touched.
"""

from __future__ import annotations

from pathlib import Path

from specy_road.finish_land_deterministic import (
    merge_feature_deterministically,
)
from specy_road.git_subprocess import git_code, git_ok


def _ref_exists_local(repo: Path, ref: str) -> bool:
    code, _ = git_code(["rev-parse", "--verify", ref], repo)
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


def integration_worktree(repo: Path, integration_branch: str) -> Path | None:
    """Another worktree with ``integration_branch`` checked out, or ``None``."""
    _ok, out = git_ok(["worktree", "list", "--porcelain"], repo)
    path: Path | None = None
    for line in out.splitlines():
        if line.startswith("worktree "):
            path = Path(line[len("worktree "):])
        elif line == f"branch refs/heads/{integration_branch}" and path is not None:
            return None if path.resolve() == repo.resolve() else path
    return None


def integration_worktree_problem(repo: Path, integration_branch: str) -> str | None:
    """Why the landing cannot run in the other worktree holding the branch, or ``None``.

    Untracked files do not count: a coordinator checkout routinely holds
    untracked pickup briefs, and a merge that would overwrite one is refused by
    git itself before it changes anything.
    """
    holder = integration_worktree(repo, integration_branch)
    if holder is None:
        return None
    _ok, out = git_ok(["status", "--porcelain", "--untracked-files=no"], holder)
    if not out:
        return None
    return (
        f"{integration_branch!r} is checked out in {holder} with uncommitted "
        "changes; finish lands the merge in that worktree and never touches "
        "another checkout's changes. Commit or stash them there, then re-run."
    )


def _merge_and_push(
    tree: Path, *, remote: str, integration_branch: str, feature_branch: str
) -> tuple[bool, str]:
    """Fast-forward, merge and push ``integration_branch``, checked out in ``tree``."""
    rr = f"{remote}/{integration_branch}"
    if _ref_exists_local(tree, f"refs/remotes/{rr}"):
        code, out = git_code(["merge", "--ff-only", rr], tree)
        if code != 0:
            return (
                False,
                f"fast-forward {integration_branch} to {rr} failed "
                f"(sync the integration branch locally, then retry): {out}",
            )
    ok, out = merge_feature_deterministically(
        tree,
        integration_branch=integration_branch,
        feature_branch=feature_branch,
    )
    if not ok:
        return False, out
    code, out = git_code(["push", remote, integration_branch], tree)
    if code != 0:
        return (
            False,
            f"git push {remote} {integration_branch} failed (local merge may exist): {out}",
        )
    return True, ""


def land_merge_feature_into_integration(
    repo: Path,
    *,
    remote: str,
    integration_branch: str,
    feature_branch: str,
) -> tuple[bool, str]:
    """
    Fetch, checkout integration, fast-forward to remote tracking ref, merge feature,
    push integration, checkout feature. When another worktree has the
    integration branch checked out, merge and push there instead (refusing if
    it has uncommitted changes) and leave this checkout alone.

    Returns (True, "") on success, (False, message) on failure. Failure
    messages are structured so callers can surface a hard error rather than
    silently falling back to PR instructions (F-012).
    """
    code, out = git_code(["fetch", remote], repo)
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

    problem = integration_worktree_problem(repo, integration_branch)
    if problem is not None:
        return False, problem
    holder = integration_worktree(repo, integration_branch)
    if holder is not None:
        return _merge_and_push(
            holder, remote=remote,
            integration_branch=integration_branch, feature_branch=feature_branch,
        )

    code, out = git_code(["checkout", integration_branch], repo)
    if code != 0:
        return False, f"git checkout {integration_branch} failed: {out}"
    ok, err = _merge_and_push(
        repo, remote=remote,
        integration_branch=integration_branch, feature_branch=feature_branch,
    )
    code, out = git_code(["checkout", feature_branch], repo)
    if not ok:
        return False, err
    if code != 0:
        return False, f"git checkout {feature_branch} after merge failed: {out}"
    return True, ""
