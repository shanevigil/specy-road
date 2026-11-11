#!/usr/bin/env python3
"""PM workflow: sync integration branch from remote, then validate, export and digest."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from specy_road.cli_entry import integration_defaults
from specy_road.runtime_paths import add_repo_root_arg, resolve_repo_root
from specy_road.repo_ops import sync_integration_branch

def _validate_export_digest(root: Path) -> None:
    """validate, export, digest — leave no generated-and-committed file stale."""
    rr = ["--repo-root", str(root)]
    for command in ("validate", "export", "digest"):
        subprocess.check_call(
            [sys.executable, "-m", "specy_road.cli", command, *rr],
            cwd=root,
        )


def build_parser() -> argparse.ArgumentParser:
    """The ``specy-road sync`` parser."""
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
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv if argv is not None else sys.argv[1:])

    root = resolve_repo_root(args)
    base, remote = integration_defaults(root, args)

    # F-010: git + a configured remote are a hard dependency. No --no-git
    # opt-out; teams that are offline must use a local bare remote.
    sync_integration_branch(
        root,
        base,
        remote,
        retry_hint="retry pm-sync",
    )

    print("-> specy-road validate")
    print("-> specy-road export")
    print("-> specy-road digest")
    _validate_export_digest(root)
    print(
        "\n[ok] roadmap validated; roadmap.md and roadmap-context.md refreshed."
    )


if __name__ == "__main__":
    main()
