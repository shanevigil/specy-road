#!/usr/bin/env python3
"""``specy-road branches prune``: deprecated alias of ``doctor --prune --kind branches``.

It prints one deprecation line, then lists the cleanup planner's branch findings
(:mod:`specy_road.cleanup_plan`) in its own selection: merged into the remote
integration branch by ancestry, with no registry row and no open milestone
rollup, and not checked out in a worktree. ``--delete`` removes exactly those.
The planner's live rule (an open claim, a running worker or a live session) and
its own-commit evidence can only narrow that selection.
"""

from __future__ import annotations

import argparse
import sys

from specy_road import cleanup_plan
from specy_road.cli import warn_deprecated
from specy_road.cli_args import add_base_arg, add_remote_arg
from specy_road.cli_entry import run_cli
from specy_road.runtime_paths import add_repo_root_arg, resolve_repo_root

PATTERN = cleanup_plan.PATTERN


def _delete(selected: list) -> int:
    """Remove each planned branch; 1 when any removal failed (each failure on stderr)."""
    failures = 0
    for f in selected:
        failure = f.remove()
        if failure is None:
            print(f"[ok] {f.done}")
        else:
            print(f"[warn] {f.branch}: {failure}", file=sys.stderr)
            failures += 1
    return 1 if failures else 0


def cmd_prune(ns: argparse.Namespace) -> int:
    warn_deprecated("branches prune", "doctor --prune --kind branches")
    ctx = cleanup_plan.context(resolve_repo_root(ns), ns)
    if ctx is None:
        return 1
    (_kind, _heading, found), = cleanup_plan.plan(ctx, {"branch"})
    selected = cleanup_plan.branches_prune_scope(ctx, found)
    if not selected:
        print(f"Nothing to prune: no unclaimed {PATTERN} branch is merged into {ctx.target}.")
        return 0
    if ns.delete:
        return _delete(selected)
    print(f"Merged into {ctx.target} and unclaimed:")
    for f in selected:
        print(f"  {f.name}")
    print("Nothing deleted. Re-run with --delete to delete them.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="specy-road")
    sub = p.add_subparsers(dest="cmd", required=True)
    br = sub.add_parser("branches", help="Tidy feature/rm-* branches.")
    bsub = br.add_subparsers(dest="branches_cmd", required=True)
    prune = bsub.add_parser(
        "prune",
        description=(
            "Deprecated: use specy-road doctor --prune --kind branches (this "
            "alias is removed in the release after 0.3.1). List feature/rm-* "
            "branches, local and on the remote, that the remote integration "
            "branch already contains, after git fetch --prune. Branches with a "
            "registry claim, open milestone rollup branches, live work and a "
            "branch a worktree has checked out are skipped. Deletes only with "
            "--delete."
        ),
    )
    prune.add_argument("--delete", action="store_true",
                       help="Delete the listed branches locally and on the remote.")
    add_base_arg(prune)
    add_remote_arg(prune)
    add_repo_root_arg(prune)
    prune.set_defaults(func=cmd_prune)
    return p


def main(argv: list[str] | None = None) -> None:
    run_cli(build_parser, argv)


if __name__ == "__main__":
    main()
