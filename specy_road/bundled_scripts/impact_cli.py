#!/usr/bin/env python3
"""CLI for ``specy-road impact``: the Python tests that import a leaf's code."""

from __future__ import annotations

import argparse
import sys

from specy_road.impact import impact_for_diff, impact_for_zones
from specy_road.review_target import resolve_target_or_exit
from specy_road.runtime_paths import add_repo_root_arg, default_user_repo_root


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(
        description="List, sorted, every Python test file that imports (at any depth) a module changed "
        "between the merge base and REF; ALL when a conftest.py changed. Advisory; git objects only.",
    )
    p.add_argument("node_id", help="Roadmap node id, e.g. M9.9")
    p.add_argument("--ref", help="Branch or commit (default: the node's registered branch)")
    p.add_argument("--zones", action="store_true",
                   help="Start from the modules under the node's touch zones at REF instead of the diff")
    add_repo_root_arg(p)
    args = p.parse_args(argv)
    root = (args.repo_root or default_user_repo_root()).resolve()
    target = resolve_target_or_exit(root, args.node_id, args.ref)
    if not target.commit or not (args.zones or target.base):
        print("error: cannot resolve merge base or commit under review", file=sys.stderr)
        raise SystemExit(1)
    if args.zones:
        impact = impact_for_zones(root, target.commit, target.touch_zones)
    else:
        impact = impact_for_diff(root, target.base, target.commit)
    if impact is None:
        print("error: git could not read the diff or the tree", file=sys.stderr)
        raise SystemExit(1)
    for line in impact.lines():
        print(line)


if __name__ == "__main__":
    main()
