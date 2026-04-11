#!/usr/bin/env python3
"""PM workflow: sync integration branch from remote, then validate and export roadmap."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from specy_road.runtime_paths import default_user_repo_root

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


def _assert_working_tree_clean() -> None:
    if not _working_tree_clean():
        print(
            "error: working tree is not clean (commit, stash, or discard changes first).",
            file=sys.stderr,
        )
        raise SystemExit(1)


def _sync_integration_branch(base: str, remote: str) -> None:
    _assert_working_tree_clean()
    _git("fetch", remote)
    _git("checkout", base)
    try:
        _git("merge", "--ff-only", f"{remote}/{base}")
    except subprocess.CalledProcessError:
        print(
            f"error: could not fast-forward local '{base}' to {remote}/{base}.",
            file=sys.stderr,
        )
        print(
            "  Resolve your local integration branch (e.g. pull with rebase, or reset "
            "after team agreement), then retry.",
            file=sys.stderr,
        )
        raise SystemExit(1)


def _validate_and_export() -> None:
    rr = ["--repo-root", str(ROOT)]
    subprocess.check_call(
        [sys.executable, "-m", "specy_road.cli", "validate", *rr],
        cwd=ROOT,
    )
    subprocess.check_call(
        [sys.executable, "-m", "specy_road.cli", "export", *rr],
        cwd=ROOT,
    )


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--base",
        default="main",
        metavar="BRANCH",
        help="Integration branch to sync (default: main).",
    )
    p.add_argument(
        "--remote",
        default="origin",
        metavar="NAME",
        help="Git remote to fetch and merge from (default: origin).",
    )
    p.add_argument(
        "--no-git",
        action="store_true",
        help="Skip git; only run validate and export (offline).",
    )
    p.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        metavar="DIR",
        help="Repository root (default: git root or cwd).",
    )
    args = p.parse_args(argv if argv is not None else sys.argv[1:])

    global ROOT
    ROOT = (args.repo_root or default_user_repo_root()).resolve()

    if not args.no_git:
        _sync_integration_branch(args.base, args.remote)

    print("-> specy-road validate")
    print("-> specy-road export")
    _validate_and_export()
    print("\n[ok] roadmap validated and markdown export refreshed.")


if __name__ == "__main__":
    main()
