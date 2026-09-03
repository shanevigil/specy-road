#!/usr/bin/env python3
"""Undo do-next-available-task pickup: deregister on integration branch, drop feature branch, clean work/."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import yaml
from specy_road.feature_rm_registry import resolve_feature_rm_registry_context
from specy_road.git_workflow_config import resolve_integration_defaults
from specy_road.registry_yaml import read_registry, registry_path, write_registry
from specy_road.on_complete_session import (
    on_complete_session_path,
    remove_on_complete_session,
)
from specy_road.runtime_paths import add_repo_root_arg, resolve_repo_root
from specy_road.bundled_scripts.repo_ops import current_branch, git_capture, git_run

#: Rebound by :func:`main` before any helper runs; this is only a placeholder
#: so the name exists at import. Resolving the real root here would make
#: importing the module shell out to git.
ROOT = Path.cwd()


def _pickup_artifact_rel_paths(node_id: str) -> set[str]:
    """The ``work/`` files pickup created for this node — the ones abort deletes."""
    return {
        f"work/brief-{node_id}.md",
        f"work/prompt-{node_id}.md",
        f"work/implementation-summary-{node_id}.md",
        on_complete_session_path(Path("work"), node_id).as_posix(),
    }


def _dirty_entries(ignore_untracked: set[str]) -> list[str]:
    """Porcelain entries that should block the abort.

    ``do-next-available-task`` writes the brief, the prompt and the session
    sidecar, and the scaffold deliberately does not gitignore the brief — so a
    pickup leaves untracked files behind and an immediate abort would refuse on
    output the toolkit itself just produced. Those specific untracked paths are
    excluded. A *modified tracked* file still blocks: that is real work, and
    abort is not the command to throw it away.
    """
    r = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    blocking: list[str] = []
    for line in (r.stdout or "").splitlines():
        if not line.strip():
            continue
        status, _, path = line[:2], line[2], line[3:]
        if status == "??" and path in ignore_untracked:
            continue
        blocking.append(line)
    return blocking


def _assert_working_tree_clean(ignore_untracked: set[str] | None = None) -> None:
    dirty = _dirty_entries(ignore_untracked or set())
    if not dirty:
        return
    print(
        "error: working tree is not clean (commit, stash, or discard changes first).",
        file=sys.stderr,
    )
    for line in dirty:
        print(f"  {line}", file=sys.stderr)
    raise SystemExit(1)


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
    git_run(ROOT, "checkout", base)
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


def main(argv: list[str] | None = None) -> None:
    global ROOT
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    ROOT = resolve_repo_root(args)

    base, remote, gw_warns = resolve_integration_defaults(
        ROOT,
        explicit_base=args.base,
        explicit_remote=args.remote,
    )
    for w in gw_warns:
        print(f"warning: {w}", file=sys.stderr)

    branch = _require_feature_rm_branch_or_exit()

    # Resolve the claim first so the cleanliness check knows which work/ files
    # belong to this pickup. Reads roadmap/registry.yaml only; no git state
    # changes before the check.
    codename, _reg_before, entry, _nodes = resolve_feature_rm_registry_context(
        ROOT,
        branch,
    )
    node_id = entry["node_id"]
    _assert_working_tree_clean(_pickup_artifact_rel_paths(node_id))

    git_run(ROOT, "fetch", remote)
    ahead = _count_commits_ahead_of_remote_base(remote, base)
    _exit_if_unpushed_commits_without_force(remote, base, ahead, args.force)

    _sync_integration_branch_ff(remote, base)
    _remove_registry_row_and_push(remote, base, codename)

    _delete_feature_branch(branch, force=args.force)
    _remove_pickup_work_files(node_id, force=args.force)

    print(f"\n[ok] pickup aborted; on branch {current_branch(ROOT)}")


if __name__ == "__main__":
    main()
