#!/usr/bin/env python3
"""Create milestone rollup branch and write work/.milestone-session.yaml."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

from roadmap_load import load_roadmap
from specy_road.git_workflow_config import resolve_integration_defaults
from specy_road.milestone_session import (
    milestone_session_path,
    write_milestone_session,
)
from specy_road.milestone_subtree import structural_leaf_ids
from specy_road.runtime_paths import default_user_repo_root

_CODENAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

ROOT = Path.cwd()


def _git(*args: str) -> None:
    subprocess.check_call(["git", *args], cwd=ROOT)


def _working_tree_clean() -> bool:
    r = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return not r.stdout.strip()


def _sync_integration_branch(base: str, remote: str) -> None:
    if not _working_tree_clean():
        print(
            "error: working tree is not clean (commit, stash, or discard changes first).",
            file=sys.stderr,
        )
        raise SystemExit(1)
    _git("fetch", remote)
    _git("checkout", base)
    try:
        _git("merge", "--ff-only", f"{remote}/{base}")
    except subprocess.CalledProcessError:
        print(
            f"error: could not fast-forward local {base!r} to {remote}/{base}.",
            file=sys.stderr,
        )
        raise SystemExit(1)


def _branch_exists(name: str) -> bool:
    r = subprocess.run(
        ["git", "rev-parse", "--verify", name],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    return r.returncode == 0


def _validate_parent(nodes: list[dict], parent_id: str) -> dict:
    by_id = {n["id"]: n for n in nodes if n.get("id")}
    if parent_id not in by_id:
        print(f"error: unknown roadmap node id {parent_id!r}.", file=sys.stderr)
        raise SystemExit(1)
    if parent_id in structural_leaf_ids(nodes):
        print(
            f"error: {parent_id!r} is a structural leaf — use a parent container "
            "(milestone/phase with children), not a leaf task.",
            file=sys.stderr,
        )
        raise SystemExit(1)
    node = by_id[parent_id]
    cn = node.get("codename")
    if not isinstance(cn, str) or not cn.strip():
        print(
            f"error: node {parent_id!r} has no codename — set `codename` on the "
            "milestone parent in the roadmap (required for branch feature/rm-<codename>).",
            file=sys.stderr,
        )
        raise SystemExit(1)
    cn = cn.strip()
    if not _CODENAME_RE.match(cn):
        print(
            f"error: codename {cn!r} must match "
            r"^[a-z0-9]+(-[a-z0-9]+)*$ (same as registry entries).",
            file=sys.stderr,
        )
        raise SystemExit(1)
    return node


def _ensure_rollup_branch(rollup: str, base: str, remote: str) -> None:
    if not _branch_exists(rollup):
        _git("checkout", "-b", rollup)
        print(f"[ok] created branch {rollup!r} from {base!r}")
        _git("checkout", base)
        return
    _git("checkout", rollup)
    try:
        _git("merge", "--ff-only", f"{remote}/{base}")
    except subprocess.CalledProcessError:
        print(
            f"error: could not fast-forward {rollup!r} to {remote}/{base}.",
            file=sys.stderr,
        )
        print(
            "  Resolve manually (e.g. merge or reset the rollup branch), then retry.",
            file=sys.stderr,
        )
        _git("checkout", base)
        raise SystemExit(1)
    print(f"[ok] fast-forwarded {rollup!r} to match {remote}/{base}")
    _git("checkout", base)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Sync integration branch, ensure rollup branch feature/rm-<parent-codename>, "
            "and write work/.milestone-session.yaml for subtree-scoped task pickup."
        ),
    )
    p.add_argument(
        "parent_node_id",
        metavar="PARENT_NODE_ID",
        help="Roadmap id of the milestone parent (e.g. M7).",
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
        help="Integration branch (default: roadmap/git-workflow.yaml).",
    )
    p.add_argument(
        "--remote",
        default=None,
        metavar="NAME",
        help="Git remote (default: roadmap/git-workflow.yaml).",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    global ROOT
    args = _parse_args(argv)
    ROOT = (args.repo_root or default_user_repo_root()).resolve()
    base, remote, gw_warns = resolve_integration_defaults(
        ROOT,
        explicit_base=args.base,
        explicit_remote=args.remote,
    )
    for w in gw_warns:
        print(f"warning: {w}", file=sys.stderr)

    data = load_roadmap(ROOT)
    nodes = data["nodes"]
    _validate_parent(nodes, args.parent_node_id)
    parent = next(n for n in nodes if n.get("id") == args.parent_node_id)
    codename = str(parent["codename"]).strip()
    rollup = f"feature/rm-{codename}"

    _sync_integration_branch(base, remote)
    _ensure_rollup_branch(rollup, base, remote)

    work_dir = ROOT / "work"
    write_milestone_session(
        milestone_session_path(work_dir),
        parent_node_id=args.parent_node_id,
        parent_codename=codename,
        integration_branch=base,
        remote=remote,
    )
    print(f"\n[ok] wrote {milestone_session_path(work_dir).relative_to(ROOT)}")
    print(f"     rollup branch: {rollup}")
    print(f"     integration:   {base} @ {remote}")
    print("\nNext:")
    print("  specy-road do-next-available-task --milestone-subtree")
    print("  # or: specy-road do-next-available-task --under", args.parent_node_id)


if __name__ == "__main__":
    main()
