#!/usr/bin/env python3
"""Enforce file-limits.yaml (per-file counts; optional Python and TS/JS function counts)."""

from __future__ import annotations

import argparse
import sys

import yaml

from specy_road.file_limits_baseline import scan_with_optional_hint, write_baseline
from specy_road.runtime_paths import add_repo_root_arg, project_root, source_scan_root


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    add_repo_root_arg(parser)
    parser.add_argument(
        "--strict-hard-alerts",
        action="store_true",
        help="Treat hard_alerts warnings as failures (exit 1).",
    )
    parser.add_argument(
        "--no-respect-gitignore",
        action="store_true",
        help=(
            "Also check files git ignores. Default: skip them, since CI never "
            "sees them (has no effect outside a git worktree)."
        ),
    )
    parser.add_argument(
        "--write-baseline",
        action="store_true",
        help=(
            "Append override_limits entries for today's failing files to "
            "constraints/file-limits.yaml (one bucket per rounded cap pair)."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="With --write-baseline, print the entries that would be appended instead of writing.",
    )
    args = parser.parse_args()
    # Two roots: the config belongs to the specy-road project, but the globs
    # inside it name the consumer's own source, which stays at the git root
    # when that project lives in a subfolder.
    project = project_root(args.repo_root)
    config_path = project / "constraints" / "file-limits.yaml"
    if not config_path.is_file():
        print(f"missing {config_path}", file=sys.stderr)
        raise SystemExit(1)
    with config_path.open(encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    respect = not args.no_respect_gitignore
    if args.write_baseline:
        raise SystemExit(
            write_baseline(
                args.repo_root,
                dry_run=args.dry_run,
                respect_gitignore=respect,
            )
        )
    config_rel = config_path.relative_to(project).as_posix()
    if scan_with_optional_hint(
        source_scan_root(project),
        cfg,
        config_rel,
        strict_hard_alerts=args.strict_hard_alerts,
        respect_gitignore=respect,
    ):
        raise SystemExit(1)
    print("OK: file limits satisfied.")


if __name__ == "__main__":
    main()
