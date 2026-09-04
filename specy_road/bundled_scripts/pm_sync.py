#!/usr/bin/env python3
"""PM workflow: sync integration branch from remote, then validate and export roadmap."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from specy_road.git_workflow_config import resolve_integration_defaults
from specy_road.runtime_paths import add_repo_root_arg, resolve_repo_root
from specy_road.bundled_scripts.repo_ops import sync_integration_branch

#: Rebound by :func:`main` before any helper runs; this is only a placeholder
#: so the name exists at import. Resolving the real root here would make
#: importing the module shell out to git.
ROOT = Path.cwd()


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
        default=None,
        metavar="BRANCH",
        help=(
            "Integration branch to sync "
            "(default: roadmap/git-workflow.yaml, else main)."
        ),
    )
    p.add_argument(
        "--remote",
        default=None,
        metavar="NAME",
        help=(
            "Git remote to fetch and merge from "
            "(default: roadmap/git-workflow.yaml, else origin)."
        ),
    )
    add_repo_root_arg(p)
    args = p.parse_args(argv if argv is not None else sys.argv[1:])

    global ROOT
    ROOT = resolve_repo_root(args)
    base, remote, gw_warns = resolve_integration_defaults(
        ROOT,
        explicit_base=args.base,
        explicit_remote=args.remote,
    )
    for w in gw_warns:
        print(f"warning: {w}", file=sys.stderr)

    # F-010: git + a configured remote are a hard dependency. No --no-git
    # opt-out; teams that are offline must use a local bare remote.
    sync_integration_branch(
        ROOT,
        base,
        remote,
        retry_hint="retry pm-sync",
    )

    print("-> specy-road validate")
    print("-> specy-road export")
    _validate_and_export()
    print("\n[ok] roadmap validated and markdown export refreshed.")


if __name__ == "__main__":
    main()
