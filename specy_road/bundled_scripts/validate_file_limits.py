#!/usr/bin/env python3
"""Enforce constraints/file-limits.yaml (line counts per glob, optional per-function for Python)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import yaml

from specy_road.file_limits_engine import run_file_limits_scan
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
    if run_file_limits_scan(
        source_scan_root(project),
        cfg,
        strict_hard_alerts=args.strict_hard_alerts,
        respect_gitignore=not args.no_respect_gitignore,
    ):
        raise SystemExit(1)
    print("OK: file limits satisfied.")


if __name__ == "__main__":
    main()
