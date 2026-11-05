#!/usr/bin/env python3
"""``specy-road worktree prune <ID>``: list what removing a leaf's worktree deletes; remove it with ``--yes``.

``worktree cleanup <ID>`` and ``worktree sweep`` retire landed worktrees after saving their hand-off files
(:mod:`specy_road.worktree_cleanup`).

The checks are :func:`specy_road.worktree_prune.plan_prune`'s: the leaf's branch
merged into the integration branch, and nothing uncommitted, untracked, stashed
or held by no branch, in the worktree or in a ``nested_repos`` repository in it,
and no other repository's worktree or checkout inside it.
"""

from __future__ import annotations

import argparse
import sys

from specy_road.cli_entry import run_cli
from specy_road.runtime_paths import add_repo_root_arg, resolve_repo_root
from specy_road.worktree_cleanup import cleanup_after_land, sweep
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


def cmd_cleanup(ns: argparse.Namespace) -> int:
    try:
        removed, lines = cleanup_after_land(resolve_repo_root(ns), ns.node_id)
    except PruneError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    if not removed:
        print(f"error: not cleaning up {ns.node_id}:", file=sys.stderr)
        for reason in lines:
            print(f"  - {reason}", file=sys.stderr)
        return 1
    for line in lines:
        print(f"[ok] {line}")
    return 0


def cmd_sweep(ns: argparse.Namespace) -> int:
    for line in sweep(resolve_repo_root(ns), dry_run=ns.dry_run, delete_branch=ns.delete_local_branch):
        print(line)
    return 0


def _add_cleanup_parsers(wsub: argparse._SubParsersAction) -> None:
    clean = wsub.add_parser(
        "cleanup",
        description=(
            "After finish-this-task lands NODE_ID: move the hand-off files in its worktree's own "
            "work/reviews/NODE_ID/ (history copies and RUN-* logs included) into the main checkout's, keeping a "
            "different same-named file beside the existing one as <name>.from-worktree<n>; then, when every "
            "`worktree prune` check passes and each ignored file left is regenerable (caches, node_modules, "
            "work/prompt-*.md, work/brief-*.md, work/.on-complete-*.yaml, .specyrd/cache/), terminate the "
            "leaf's idle worker, remove the worktree and end the session records tied to it or its branch. "
            "Otherwise removes nothing and prints one line per reason."
        ),
    )
    clean.set_defaults(func=cmd_cleanup)
    clean.add_argument("node_id", metavar="NODE_ID")
    add_repo_root_arg(clean)
    sw = wsub.add_parser(
        "sweep",
        description=(
            "For every linked worktree, wherever it lives, whose branch or detached HEAD the integration "
            "branch contains and that no registry claim, worker or live session holds: save its hand-off "
            "files and remove it under the cleanup rules. Prints one line per worktree: removed, would "
            "remove, or kept with the reason. Ends orphaned workers first. Never deletes a remote branch."
        ),
    )
    sw.set_defaults(func=cmd_sweep)
    sw.add_argument("--dry-run", action="store_true", help="Report only; move and remove nothing.")
    sw.add_argument("--delete-local-branch", action="store_true",
                    help="Also delete each removed worktree's local branch, only when the integration branch contains it.")
    add_repo_root_arg(sw)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="specy-road")
    sub = p.add_subparsers(dest="cmd", required=True)
    wt = sub.add_parser("worktree", help="Retire a leaf's worktree, or sweep landed ones.")
    wsub = wt.add_subparsers(dest="worktree_cmd", required=True)
    prune = wsub.add_parser(
        "prune",
        description=(
            "Remove work/.worktrees/<codename> for NODE_ID only when the worktree's HEAD and "
            "feature/rm-<codename>, local, remote-tracking and on the remote wherever they exist, are "
            "merged into the remote's actual integration tip (read with git ls-remote whatever the "
            "fetch refspec says, its commits fetched by name; a remote that cannot be read refuses), and "
            "it has no uncommitted changes, untracked non-ignored files, or stashes whose subject does not name another branch. Each nested_repos "
            "repository in it must also hold no uncommitted changes, stashes, or commits that no "
            "branch or remote-tracking ref of the main checkout's copy holds (a full clone's own "
            "branches and remote-tracking refs included). Any other directory in it holding a .git (another "
            "repository's linked worktree, checkout or submodule) or a bare repository, found by walking "
            "the filesystem, refuses, as does a directory that walk cannot read, naming its repository, branch and the commits "
            "its upstream lacks. Lists each ignored file removal deletes, "
            "including those inside ignored directories; removes only with --yes."
        ),
    )
    prune.set_defaults(func=cmd_prune)
    prune.add_argument("node_id", metavar="NODE_ID")
    prune.add_argument("--yes", action="store_true", help="Remove the worktree after the checks pass.")
    add_repo_root_arg(prune)
    _add_cleanup_parsers(wsub)
    return p


def main(argv: list[str] | None = None) -> None:
    run_cli(build_parser, argv)


if __name__ == "__main__":
    main()
