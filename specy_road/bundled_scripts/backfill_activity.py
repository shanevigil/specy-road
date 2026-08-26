#!/usr/bin/env python3
"""Seed roadmap/activity.json from git history (see specy_road/activity_backfill.py)."""

from __future__ import annotations

import argparse
from pathlib import Path

from specy_road.activity_backfill import backfill_activity
from specy_road.runtime_paths import default_user_repo_root


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(
        prog="specy-road backfill-activity",
        description=__doc__,
    )
    p.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        metavar="DIR",
        help="Repository root (default: git root or cwd).",
    )
    p.add_argument(
        "--dry-run", action="store_true", help="Show what would be recorded."
    )
    ns = p.parse_args(argv)
    root = (ns.repo_root or default_user_repo_root()).resolve()
    out = backfill_activity(root, dry_run=ns.dry_run)

    for node_id, _key, when in out["entries"]:
        print(f"  {node_id:<10} {when}")
    if ns.dry_run:
        print(f"\n[dry run] {out['candidates']} node(s) datable from git history.")
        return
    print(
        f"\n[ok] recorded {out['applied']} of {out['candidates']} node(s) "
        "as kind=backfilled (a lower bound on real activity)."
    )


if __name__ == "__main__":
    main()
