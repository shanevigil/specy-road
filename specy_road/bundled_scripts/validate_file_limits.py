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
from specy_road.runtime_paths import default_user_repo_root


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        metavar="DIR",
        help="Repository root (default: git root or cwd).",
    )
    parser.add_argument(
        "--strict-hard-alerts",
        action="store_true",
        help="Treat hard_alerts warnings as failures (exit 1).",
    )
    args = parser.parse_args()
    root = (args.repo_root or default_user_repo_root()).resolve()
    config_path = root / "constraints" / "file-limits.yaml"
    if not config_path.is_file():
        print(f"missing {config_path}", file=sys.stderr)
        raise SystemExit(1)
    with config_path.open(encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    if run_file_limits_scan(
        root,
        cfg,
        strict_hard_alerts=args.strict_hard_alerts,
    ):
        raise SystemExit(1)
    print("OK: file limits satisfied.")


if __name__ == "__main__":
    main()
