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

from specy_road.runtime_paths import git_root, project_prefix
from specy_road.finish_land_check import resolve_land_check_cmd, run_land_check
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


def holder_project_root(repo: Path, holder: Path) -> Path:
    """The project root inside ``holder``, another worktree of the same repository.

    ``git worktree list`` names the holder's git root; ``repo`` is this
    checkout's project root, which in the nested layout sits below its git
    root. The landing resolves registry and generated files relative to the
    project root, so it must run there in the holder too.
    """
    return holder / project_prefix(repo)


def integration_worktree(repo: Path, integration_branch: str) -> Path | None:
    """Another worktree with ``integration_branch`` checked out, or ``None``.

    ``git worktree list`` names git roots. ``repo`` is the project root, which
    in the nested layout sits below its git root. Compare those roots: this
    checkout is not another worktree, so a later delete switches it onto the
    integration branch instead of detaching.
    """
    here = git_root(repo)
    _ok, out = git_ok(["worktree", "list", "--porcelain"], repo)
    path: Path | None = None
    for line in out.splitlines():
        if line.startswith("worktree "):
            path = Path(line[len("worktree "):])
        elif line == f"branch refs/heads/{integration_branch}" and path is not None:
            return None if path.resolve() == here else path
    return None


def integration_worktree_problem(repo: Path, integration_branch: str) -> str | None:
    """Why the landing cannot run in the other worktree holding the branch, or ``None``.

    Untracked files do not count: a coordinator checkout routinely holds
    untracked pickup briefs, and a merge that would overwrite one is refused by
    git itself before it changes anything -- except ``roadmap.md`` and
    ``roadmap-context.md``, which the landing regenerates in place.
    """
    holder = integration_worktree(repo, integration_branch)
    if holder is None:
        return None
    ok, out = git_ok(["status", "--porcelain", "--untracked-files=no"], holder)
    if not ok:
        return (
            f"{integration_branch!r} is checked out in {holder}, but could not read "
            f"the status of {holder} ({out or 'git did not run'}); finish lands the "
            "merge there only when it is known to be clean. Fix or prune that "
            "worktree, then re-run."
        )
    if not out:
        return None
    return (
        f"{integration_branch!r} is checked out in {holder} with uncommitted "
        "changes; finish lands the merge in that worktree and never touches "
        "another checkout's changes. Commit or stash them there, then re-run."
    )


def _reset_integration(tree: Path, integration_branch: str, pre: str) -> str:
    """Put ``integration_branch`` (checked out in ``tree``) back at ``pre``; a note on failure."""
    code, out = git_code(["reset", "--keep", pre], tree)
    if code == 0:
        return f"Local {integration_branch} is back at {pre[:12]}."
    return f"Resetting local {integration_branch} to {pre[:12]} also failed: {out}"


def tracking_ref_snapshot(repo: Path, *, remote: str, integration_branch: str) -> str:
    """The commit ``remote/integration_branch`` names, or ``""`` when that ref does not exist.

    Taken before finish's first fetch, so a failed land check can put the ref
    back where finish found it.
    """
    ref = f"refs/remotes/{remote}/{integration_branch}"
    ok, sha = git_ok(["rev-parse", "--verify", "--quiet", ref], repo)
    return sha if ok else ""


def _restore_tracking(tree: Path, remote: str, integration_branch: str, before: str) -> str:
    """Put ``remote/integration_branch`` back at ``before`` (absent when ``""``); a note either way."""
    ref = f"refs/remotes/{remote}/{integration_branch}"
    code, out = git_code(["update-ref", ref, before] if before else ["update-ref", "-d", ref], tree)
    if code != 0:
        return f"Restoring {remote}/{integration_branch} also failed: {out}"
    return f"{remote}/{integration_branch} is back at {before[:12] or 'its absence'}."


def _merge_and_push(
    tree: Path, *, remote: str, integration_branch: str, feature_branch: str,
    land_check_cmd: str | None = None, tracking_before: str = "",
) -> tuple[bool, str]:
    """Fast-forward, merge, land-check and push ``integration_branch``, checked out in ``tree``.

    A failed land check or a rejected push resets the local integration branch
    to where it was before this landing, so a re-run merges onto the remote's
    new tip and checks that commit instead. The push is the compare-and-swap:
    a tip that moved since the check makes it fail. A failed land check also
    puts ``remote/integration_branch`` back at ``tracking_before``, undoing
    finish's fetch, because it pushed nothing.
    """
    _ok, pre = git_ok(["rev-parse", "HEAD"], tree)
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
    if land_check_cmd:
        problem = run_land_check(tree, land_check_cmd)
        if problem is not None:
            return False, (
                f"{problem}\n  {_reset_integration(tree, integration_branch, pre)} "
                f"{_restore_tracking(tree, remote, integration_branch, tracking_before)}"
            )
    code, out = git_code(["push", remote, integration_branch], tree)
    if code != 0:
        return (
            False,
            f"git push {remote} {integration_branch} failed: {out}\n  "
            f"{_reset_integration(tree, integration_branch, pre)} If {rr} moved, "
            "re-running merges onto its new tip and runs the land check again.",
        )
    return True, ""


def integration_commits_ahead_of_remote(
    repo: Path, *, remote: str, integration_branch: str,
) -> int | None:
    """How many commits on the local integration branch are not on ``remote/integration_branch``."""
    local = f"refs/heads/{integration_branch}"
    tracked = f"refs/remotes/{remote}/{integration_branch}"
    if not _ref_exists_local(repo, local):
        return None
    if not _ref_exists_local(repo, tracked):
        return None
    code, out = git_code(["rev-list", "--count", f"{tracked}..{integration_branch}"], repo)
    if code != 0 or not out.strip().isdigit():
        return None
    return int(out.strip())


def _ref_sha(repo: Path, ref: str) -> str | None:
    ok, sha = git_ok(["rev-parse", "--verify", "--quiet", ref], repo)
    return sha if ok else None


def _is_ancestor(repo: Path, ancestor: str, descendant: str) -> bool:
    ok, _ = git_ok(["merge-base", "--is-ancestor", ancestor, descendant], repo)
    return ok


def _rev_list_count(
    repo: Path, tips: list[str], exclude: list[str] | None = None,
) -> int:
    """Count commits reachable from ``tips``, optionally excluding ``exclude``.

    ``exclude is None`` counts the entire reachable set (no remote-tracking
    baseline). Shared ancestry across ``tips`` is counted once.
    """
    args = ["rev-list", "--count", *tips]
    if exclude is not None:
        args += ["--not", *exclude]
    code, out = git_code(args, repo)
    if code != 0 or not out.strip().isdigit():
        return 0
    return int(out.strip())


def _integration_tip_after_ff(
    repo: Path, *, remote: str, integration_branch: str,
) -> str | None:
    """Integration ``HEAD`` after the landing's ``merge --ff-only`` to the tracking ref."""
    local = _ref_sha(repo, f"refs/heads/{integration_branch}")
    tracked = _ref_sha(repo, f"refs/remotes/{remote}/{integration_branch}")
    if local and tracked:
        if _is_ancestor(repo, local, tracked):
            return tracked
        if _is_ancestor(repo, tracked, local):
            return local
        return local
    return local or tracked


def _feature_merge_adds_commit(repo: Path, integration_tip: str, feature_branch: str) -> bool:
    ok, _ = git_ok(["merge-base", "--is-ancestor", feature_branch, integration_tip], repo)
    return not ok


def merge_push_disclosure_counts(
    repo: Path, *, remote: str, integration_branch: str, feature_branch: str,
) -> tuple[int, int]:
    """Return ``(total_commits_on_push, not_from_leaf)`` for merge-mode disclosure.

    ``total`` is every commit newly reachable on the pushed integration ref:
    local integration history, feature-only commits, and the landing merge
    commit, with shared ancestry counted once. ``not_from_leaf`` is the subset
    not reachable from ``feature_branch``.
    """
    integration_tip = _integration_tip_after_ff(
        repo, remote=remote, integration_branch=integration_branch,
    )
    if integration_tip is None:
        return 0, 0
    tracked = _ref_sha(repo, f"refs/remotes/{remote}/{integration_branch}")
    baseline = [tracked] if tracked is not None else None
    not_from_exclude = [*(baseline or []), feature_branch]
    not_from_leaf = _rev_list_count(repo, [integration_tip], exclude=not_from_exclude)
    total = _rev_list_count(
        repo, [integration_tip, feature_branch], exclude=baseline,
    )
    if _feature_merge_adds_commit(repo, integration_tip, feature_branch):
        total += 1
    return total, not_from_leaf


def print_merge_push_notice(
    repo: Path, *, remote: str, integration_branch: str, feature_branch: str,
) -> None:
    """Tell the operator what merge mode will push before it runs."""
    git_code(["fetch", remote], repo)
    total, not_from_leaf = merge_push_disclosure_counts(
        repo,
        remote=remote,
        integration_branch=integration_branch,
        feature_branch=feature_branch,
    )
    print(
        f"\nMerge mode will merge {feature_branch!r} into {integration_branch!r} "
        f"and push {remote}/{integration_branch}."
    )
    total_word = "commit" if total == 1 else "commits"
    print(
        f"  The push will carry {total} {total_word} "
        f"({not_from_leaf} not from {feature_branch!r})."
    )


def land_merge_feature_into_integration(
    repo: Path,
    *,
    remote: str,
    integration_branch: str,
    feature_branch: str,
    land_check_cmd: str | None = None,
    tracking_before: str | None = None,
) -> tuple[bool, str]:
    """
    Fetch, checkout integration, fast-forward to remote tracking ref, merge feature,
    push integration, checkout feature. When another worktree has the
    integration branch checked out, merge and push there instead (refusing if
    it has uncommitted changes) and leave this checkout alone.

    ``land_check_cmd`` is the ``--land-check-cmd`` value: ``None`` falls back
    to ``land_check_cmd`` in ``roadmap/git-workflow.yaml``, ``""`` skips the
    check (:mod:`specy_road.finish_land_check`). ``tracking_before`` is the
    :func:`tracking_ref_snapshot` the caller took before its own first fetch;
    ``None`` takes it here, before this function's fetch.

    Returns (True, "") on success, (False, message) on failure. Failure
    messages are structured so callers can surface a hard error rather than
    silently falling back to PR instructions (F-012).
    """
    if tracking_before is None:
        tracking_before = tracking_ref_snapshot(
            repo, remote=remote, integration_branch=integration_branch,
        )
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
    check = resolve_land_check_cmd(repo, cli=land_check_cmd)
    holder = integration_worktree(repo, integration_branch)
    if holder is not None:
        return _merge_and_push(
            holder_project_root(repo, holder), remote=remote,
            integration_branch=integration_branch, feature_branch=feature_branch,
            land_check_cmd=check, tracking_before=tracking_before,
        )

    code, out = git_code(["checkout", integration_branch], repo)
    if code != 0:
        return False, f"git checkout {integration_branch} failed: {out}"
    ok, err = _merge_and_push(
        repo, remote=remote,
        integration_branch=integration_branch, feature_branch=feature_branch,
        land_check_cmd=check, tracking_before=tracking_before,
    )
    code, out = git_code(["checkout", feature_branch], repo)
    if not ok:
        return False, err
    if code != 0:
        return False, f"git checkout {feature_branch} after merge failed: {out}"
    return True, ""
