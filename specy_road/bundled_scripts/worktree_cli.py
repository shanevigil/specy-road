#!/usr/bin/env python3
"""``specy-road worktree prune <ID>``: list what removing a leaf's worktree deletes; remove it with ``--yes``.

The checks are :func:`specy_road.worktree_prune.plan_prune`'s: the leaf's branch
merged into the integration branch, and nothing uncommitted, untracked, stashed
or held by no branch, in the worktree or in a ``nested_repos`` repository in it.
"""

from __future__ import annotations

import argparse
import sys

from specy_road.runtime_paths import add_repo_root_arg, resolve_repo_root
from specy_road.worktree_prune import PruneError, plan_prune, remove


def cmd_prune(ns: argparse.Namespace) -> int:
    try:
        plan = plan_prune(resolve_repo_root(ns), ns.node_id)
    except PruneError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    if plan.refusals:
        print(f"error: not removing {plan.worktree}:", file=sys.stderr)
        for reason in plan.refusals:
            print(f"  - {reason}", file=sys.stderr)
        return 1
    print(f"{plan.worktree} ({plan.branch}) is merged and holds no unsaved work.")
    for _src, d, linked in plan.nested:
        print(f"  nested {'worktree' if linked else 'clone'} {d} goes with it")
    if plan.ignored:
        print("Removing it deletes these ignored files:")
        for path in plan.ignored:
            print(f"  {path}")
    else:
        print("It holds no ignored files.")
    if not ns.yes:
        print("Nothing removed. Re-run with --yes to remove it.")
        return 0
    failure = remove(plan)
    if failure:
        print(f"error: {failure}", file=sys.stderr)
        return 1
    print(f"[ok] removed worktree {plan.worktree}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="specy-road")
    sub = p.add_subparsers(dest="cmd", required=True)
    wt = sub.add_parser("worktree", help="Retire a leaf's worktree.")
    wsub = wt.add_subparsers(dest="worktree_cmd", required=True)
    prune = wsub.add_parser(
        "prune",
        description=(
            "Remove work/.worktrees/<codename> for NODE_ID only when the worktree's HEAD and "
            "feature/rm-<codename>, local and on the remote wherever they exist, are merged into the "
            "remote's integration branch, read by git fetch --prune (a failed fetch refuses), and it "
            "has no uncommitted changes, untracked non-ignored "
            "files, or stashes whose subject does not name another branch. Each nested_repos "
            "repository in it must also hold no uncommitted changes, stashes, or commits that no "
            "branch or remote-tracking ref of the main checkout's copy holds (a full clone's own "
            "branches and remote-tracking refs included). Lists each ignored file removal deletes, "
            "including those inside ignored directories; removes only with --yes."
        ),
    )
    prune.add_argument("node_id", metavar="NODE_ID")
    prune.add_argument("--yes", action="store_true", help="Remove the worktree after the checks pass.")
    add_repo_root_arg(prune)
    prune.set_defaults(func=cmd_prune)
    return p


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    ns = build_parser().parse_args(argv)
    raise SystemExit(ns.func(ns))


if __name__ == "__main__":
    main()
