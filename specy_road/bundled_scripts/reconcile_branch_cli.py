#!/usr/bin/env python3
"""CLI for ``specy-road reconcile-branch`` (see :mod:`specy_road.reconcile_branch`)."""

from __future__ import annotations

import argparse
import sys

from specy_road.git_workflow_config import resolve_integration_defaults
from specy_road.reconcile_branch import reconcile_branch
from specy_road.runtime_paths import add_repo_root_arg, resolve_repo_root


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="specy-road reconcile-branch",
        description=(
            "In a leaf's worktree: fetch the integration branch and merge it into the feature "
            "branch, resolving roadmap/registry.yaml by rule and regenerating roadmap.md and "
            "roadmap-context.md; commit, and push when the branch has an upstream. Any other "
            "conflict aborts the merge and exits 1."
        ),
    )
    add_repo_root_arg(p)
    p.add_argument("node_id", nargs="?", default=None, metavar="NODE_ID",
                   help="Refuse unless HEAD is this leaf's feature branch.")
    p.add_argument("--base", default=None, metavar="BRANCH",
                   help="Integration branch (default: roadmap/git-workflow.yaml, else main).")
    p.add_argument("--remote", default=None, metavar="NAME",
                   help="Git remote (default: roadmap/git-workflow.yaml, else origin).")
    return p.parse_args(argv)


def _codename(root, node_id: str | None) -> str | None:
    if node_id is None:
        return None
    from specy_road.bundled_scripts.roadmap_load import load_roadmap

    node = next((n for n in load_roadmap(root)["nodes"] if n.get("id") == node_id), None)
    if node is None or not node.get("codename"):
        raise SystemExit(f"error: no leaf {node_id!r} with a codename in the roadmap.")
    return node["codename"]


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    root = resolve_repo_root(args)
    base, remote, warns = resolve_integration_defaults(root, explicit_base=args.base, explicit_remote=args.remote)
    for w in warns:
        print(f"warning: {w}", file=sys.stderr)
    raise SystemExit(reconcile_branch(root, ib=base, remote=remote, codename=_codename(root, args.node_id)))


if __name__ == "__main__":
    main()
