#!/usr/bin/env python3
"""Undo do-next-available-task pickup: deregister on integration branch, drop feature branch, clean work/."""

from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
from pathlib import Path

from specy_road.feature_rm_registry import resolve_feature_rm_registry_context
from specy_road.finish_land_integration import integration_worktree
from specy_road.git_workflow_config import resolve_integration_defaults
from specy_road.registry_yaml import read_registry, registry_path, write_registry
from specy_road.on_complete_session import (
    on_complete_session_path,
    remove_on_complete_session,
)
from specy_road.runtime_paths import add_repo_root_arg, resolve_repo_root
from specy_road.bundled_scripts.abort_task_pickup_own_commit import only_own_registration_ahead
from specy_road.bundled_scripts.repo_ops import current_branch, git_capture, git_run
from specy_road.repo_lock import pickup_finish_lock

#: Rebound by :func:`main` before any helper runs; this is only a placeholder
#: so the name exists at import. Resolving the real root here would make
#: importing the module shell out to git.
ROOT = Path.cwd()


#: Why a tracked change blocks, by porcelain status letter (index, then worktree).
_STAGED = {"M": "staged edit", "A": "staged new file", "D": "staged deletion",
           "R": "staged rename", "C": "staged copy", "T": "staged type change"}
_UNSTAGED = {"M": "unstaged edit", "D": "unstaged deletion", "T": "unstaged type change"}


def _why_blocking(xy: str) -> str:
    if "U" in xy or xy in ("AA", "DD"):
        return "unmerged (conflict)"
    reasons = [_STAGED.get(xy[0]), _UNSTAGED.get(xy[1])]
    return ", ".join(r for r in reasons if r) or f"status {xy.strip()}"


def _tracked_changes() -> list[str]:
    """Tracked changes, each with why it blocks: the only thing abort refuses on.

    Pickup refuses on nothing under ``work/``, so it leaves its brief there
    untracked and a coordinator's notes may sit beside it. Untracked files
    survive the checkout abort makes: git refuses a checkout, or the ``reset
    --keep`` of a ``--local`` claim, that would overwrite one (see
    :func:`_git_keeping_untracked`), so none of them block. A tracked change
    does, under ``work/`` too: the checkout would carry it to the integration
    branch or stop on it.
    """
    out = git_capture(ROOT, "status", "--porcelain", "--untracked-files=no")
    return [f"{line[3:]} ({_why_blocking(line[:2])})" for line in out.splitlines() if line.strip()]


def _assert_no_tracked_changes(base: str) -> None:
    blocking = _tracked_changes()
    if not blocking:
        return
    print(f"error: tracked changes block abort-task-pickup: it checks out '{base}', which would "
          "carry them there or discard them.", file=sys.stderr)
    for entry in blocking:
        print(f"  {entry}", file=sys.stderr)
    print("  Commit or discard them, then retry; untracked files never block (they survive the checkout).",
          file=sys.stderr)
    raise SystemExit(1)


def _git_keeping_untracked(what: str, *args: str, retry: str = "retry abort-task-pickup") -> None:
    """Run a git step that refuses rather than overwrite an untracked file; exit 1 cleanly if it does."""
    try:
        git_run(ROOT, *args)
    except subprocess.CalledProcessError:
        print(f"error: could not {what}; git's message above names the paths.", file=sys.stderr)
        print(f"  An untracked file there would be overwritten: move it aside, then {retry}.", file=sys.stderr)
        raise SystemExit(1) from None


def _checkout_base(base: str) -> None:
    _git_keeping_untracked(f"check out '{base}'", "checkout", base)


def _save_registry(doc: dict) -> None:
    write_registry(registry_path(ROOT), doc)


def _count_commits_ahead_of_remote_base(remote: str, base: str) -> int:
    upstream = f"{remote}/{base}"
    out = git_capture(ROOT, "rev-list", "--count", f"{upstream}..HEAD").strip()
    return int(out) if out else 0


def _log_commits_ahead_of_remote_base(remote: str, base: str) -> str:
    upstream = f"{remote}/{base}"
    r = subprocess.run(
        ["git", "log", "--oneline", "--no-decorate", f"{upstream}..HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return (r.stdout or "").strip()


def _sync_integration_branch_ff(remote: str, base: str) -> None:
    _checkout_base(base)
    try:
        git_run(ROOT, "merge", "--ff-only", f"{remote}/{base}")
    except subprocess.CalledProcessError:
        print(
            f"error: could not fast-forward local '{base}' to {remote}/{base}.",
            file=sys.stderr,
        )
        print(
            "  Resolve your local integration branch, then retry abort-task-pickup.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None


def _delete_feature_branch(branch: str, *, force: bool) -> None:
    if force:
        git_run(ROOT, "branch", "-D", branch)
        return
    r = subprocess.run(
        ["git", "branch", "-d", branch],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if r.returncode == 0:
        return
    print(
        f"warning: could not delete branch with -d ({r.stderr or 'git branch -d failed'}).",
        file=sys.stderr,
    )
    print(f"  Remove it manually: git branch -D {branch}", file=sys.stderr)


def _remove_pickup_work_files(node_id: str, *, force: bool) -> None:
    work_dir = ROOT / "work"
    for name in (
        f"brief-{node_id}.md",
        f"prompt-{node_id}.md",
    ):
        p = work_dir / name
        if p.is_file():
            p.unlink()
            print(f"[ok] removed work/{name}")
    remove_on_complete_session(on_complete_session_path(work_dir, node_id))
    if force:
        summary = work_dir / f"implementation-summary-{node_id}.md"
        if summary.is_file():
            summary.unlink()
            print(f"[ok] removed work/implementation-summary-{node_id}.md")


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Abort a do-next-available-task pickup: remove registry row on the integration "
            "branch (commit + push), delete the local feature/rm-* branch, and remove pickup "
            "files under work/."
        ),
    )
    add_repo_root_arg(p)
    p.add_argument(
        "--base",
        default=None,
        metavar="BRANCH",
        help="Integration branch (default: roadmap/git-workflow.yaml, else main).",
    )
    p.add_argument(
        "--remote",
        default=None,
        metavar="NAME",
        help="Git remote (default: roadmap/git-workflow.yaml, else origin).",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help=(
            "Allow abort when this branch has commits not on the remote integration branch "
            "(deletes the local feature branch with git branch -D; may drop commits). "
            "Also removes work/implementation-summary-<NODE_ID>.md if present."
        ),
    )
    return p.parse_args(argv)


def _require_feature_rm_branch_or_exit() -> str:
    branch = current_branch(ROOT)
    if branch == "HEAD":
        print(
            "error: detached HEAD — check out your feature/rm-<codename> branch first.",
            file=sys.stderr,
        )
        raise SystemExit(1)
    if not branch.startswith("feature/rm-"):
        print(
            f"error: current branch {branch!r} is not a roadmap feature branch "
            "(expected feature/rm-<codename>).",
            file=sys.stderr,
        )
        raise SystemExit(1)
    return branch


def _exit_if_unpushed_commits_without_force(
    remote: str, base: str, ahead: int, force: bool
) -> None:
    if ahead == 0 or force:
        if ahead > 0 and force:
            print(
                f"warning: aborting despite {ahead} local commit(s) not on {remote}/{base} "
                "(feature branch will be deleted with -D).",
                file=sys.stderr,
            )
        return
    print(
        "error: this branch has commits that are not on "
        f"{remote}/{base} ({ahead} commit(s)).",
        file=sys.stderr,
    )
    log_excerpt = _log_commits_ahead_of_remote_base(remote, base)
    if log_excerpt:
        print("  Local commits not in remote integration branch:", file=sys.stderr)
        for line in log_excerpt.splitlines()[:20]:
            print(f"    {line}", file=sys.stderr)
        if ahead > 20:
            print("    ...", file=sys.stderr)
    print(
        "  Merge or push your work elsewhere, or run with --force to abandon "
        "the local feature branch (destructive).",
        file=sys.stderr,
    )
    raise SystemExit(1)


def _drop_local_registration(remote: str, base: str, branch: str) -> None:
    _checkout_base(base)
    # --keep, not --hard: --hard silently overwrites an untracked file at a path
    # the advanced remote base now tracks. The tree has no tracked changes here.
    _git_keeping_untracked(f"reset '{base}' to {remote}/{base}", "reset", "--keep", f"{remote}/{base}",
                           retry=f"`git checkout {branch}` and retry abort-task-pickup")
    print(
        f"[ok] the claim was never pushed (--local pickup): dropped its registration "
        f"commit from local {base}; nothing pushed"
    )


def _remove_registry_row_and_push(remote: str, base: str, codename: str) -> None:
    reg = read_registry(registry_path(ROOT))
    entries = reg.get("entries") or []
    if not next((e for e in entries if e.get("codename") == codename), None):
        print(
            f"error: no registry entry for codename '{codename}' after syncing "
            f"{base!r} — it may already be removed on the remote.",
            file=sys.stderr,
        )
        print(
            "  Check roadmap/registry.yaml and teammates' changes; clean up locally if needed.",
            file=sys.stderr,
        )
        raise SystemExit(1)
    reg["entries"] = [e for e in entries if e.get("codename") != codename]
    _save_registry(reg)
    rel_reg = str(registry_path(ROOT).relative_to(ROOT))
    git_run(ROOT, "add", rel_reg)
    git_run(ROOT, "commit", "-m", f"chore(rm-{codename}): abort task pickup")
    print(f"-> git push {remote} {base}")
    git_run(ROOT, "push", remote, base)


def _exit_if_base_checked_out_elsewhere(base: str, branch: str, node_id: str) -> None:
    """Abort moves this checkout to ``base``; git refuses while another worktree holds it.

    The hint's ``--force`` is what lets git remove the worktree at all: pickup
    leaves its brief there untracked, and tracked changes were refused already.
    """
    holder = integration_worktree(ROOT, base)
    if holder is None:
        return
    wt = shlex.quote(git_capture(ROOT, "rev-parse", "--show-toplevel").strip())
    print(f"error: '{base}' is checked out in {holder}, and abort-task-pickup needs it here.", file=sys.stderr)
    print("  For a delegated leaf: `specy-road worker terminate <W>`; then, in that checkout:", file=sys.stderr)
    print(f"  `git -C {wt} status --short` lists what removing this worktree discards: pickup's untracked "
          f"work/brief-{node_id}.md, and --force discards any other untracked file there too.", file=sys.stderr)
    print(f"  `git worktree remove --force {wt}`, `git checkout {branch}`, and `specy-road abort-task-pickup`.",
          file=sys.stderr)
    raise SystemExit(1)


def main(argv: list[str] | None = None) -> None:
    global ROOT
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    ROOT = resolve_repo_root(args)
    with pickup_finish_lock(ROOT, operation="abort-task-pickup"):
        _abort_locked(args)


def _abort_locked(args) -> None:
    base, remote, gw_warns = resolve_integration_defaults(
        ROOT,
        explicit_base=args.base,
        explicit_remote=args.remote,
    )
    for w in gw_warns:
        print(f"warning: {w}", file=sys.stderr)

    branch = _require_feature_rm_branch_or_exit()

    # Reads roadmap/registry.yaml only; no git state changes before the check.
    codename, _reg_before, entry, _nodes = resolve_feature_rm_registry_context(
        ROOT,
        branch,
    )
    node_id = entry["node_id"]
    _assert_no_tracked_changes(base)
    _exit_if_base_checked_out_elsewhere(base, branch, node_id)

    git_run(ROOT, "fetch", remote)
    local_claim = all(
        only_own_registration_ahead(ROOT, remote, base, codename, ref, capture=git_capture)
        for ref in ("HEAD", base)
    )
    if local_claim:
        _drop_local_registration(remote, base, branch)
    else:
        ahead = _count_commits_ahead_of_remote_base(remote, base)
        _exit_if_unpushed_commits_without_force(remote, base, ahead, args.force)
        _sync_integration_branch_ff(remote, base)
        _remove_registry_row_and_push(remote, base, codename)

    _delete_feature_branch(branch, force=args.force or local_claim)
    _remove_pickup_work_files(node_id, force=args.force)

    print(f"\n[ok] pickup aborted; on branch {current_branch(ROOT)}")


if __name__ == "__main__":
    main()
