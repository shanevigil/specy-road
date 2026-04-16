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
from specy_road.on_complete_session import (
    on_complete_session_path,
    remove_on_complete_session,
)
from specy_road.runtime_paths import default_user_repo_root

ROOT = Path.cwd()
REGISTRY_PATH = ROOT / "roadmap" / "registry.yaml"


def _git(*args: str) -> None:
    subprocess.check_call(["git", *args], cwd=ROOT)


def _git_capture(*args: str) -> str:
    r = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return r.stdout


def _current_branch() -> str:
    return _git_capture("rev-parse", "--abbrev-ref", "HEAD").strip()


def _working_tree_clean() -> bool:
    r = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return not r.stdout.strip()


def _assert_working_tree_clean() -> None:
    if not _working_tree_clean():
        print(
            "error: working tree is not clean (commit, stash, or discard changes first).",
            file=sys.stderr,
        )
        raise SystemExit(1)


def _load_registry() -> dict:
    if not REGISTRY_PATH.is_file():
        return {"version": 1, "entries": []}
    with REGISTRY_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {"version": 1, "entries": []}


def _save_registry(doc: dict) -> None:
    with REGISTRY_PATH.open("w", encoding="utf-8") as f:
        yaml.dump(doc, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def _count_commits_ahead_of_remote_base(remote: str, base: str) -> int:
    upstream = f"{remote}/{base}"
    out = _git_capture("rev-list", "--count", f"{upstream}..HEAD").strip()
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
    _git("checkout", base)
    try:
        _git("merge", "--ff-only", f"{remote}/{base}")
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
        _git("branch", "-D", branch)
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
    p.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        metavar="DIR",
        help="Repository root (default: git root or cwd).",
    )
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
    branch = _current_branch()
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
    reg = _load_registry()
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
    rel_reg = str(REGISTRY_PATH.relative_to(ROOT))
    _git("add", rel_reg)
    _git("commit", "-m", f"chore(rm-{codename}): abort task pickup")
    print(f"-> git push {remote} {base}")
    _git("push", remote, base)


def main(argv: list[str] | None = None) -> None:
    global ROOT, REGISTRY_PATH
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    ROOT = (args.repo_root or default_user_repo_root()).resolve()
    REGISTRY_PATH = ROOT / "roadmap" / "registry.yaml"

    base, remote, gw_warns = resolve_integration_defaults(
        ROOT,
        explicit_base=args.base,
        explicit_remote=args.remote,
    )
    for w in gw_warns:
        print(f"warning: {w}", file=sys.stderr)

    _assert_working_tree_clean()
    branch = _require_feature_rm_branch_or_exit()

    codename, _reg_before, entry, _nodes = resolve_feature_rm_registry_context(
        ROOT,
        branch,
    )
    node_id = entry["node_id"]

    _git("fetch", remote)
    ahead = _count_commits_ahead_of_remote_base(remote, base)
    _exit_if_unpushed_commits_without_force(remote, base, ahead, args.force)

    _sync_integration_branch_ff(remote, base)
    _remove_registry_row_and_push(remote, base, codename)

    _delete_feature_branch(branch, force=args.force)
    _remove_pickup_work_files(node_id, force=args.force)

    print(f"\n[ok] pickup aborted; on branch {_current_branch()}")


if __name__ == "__main__":
    main()
