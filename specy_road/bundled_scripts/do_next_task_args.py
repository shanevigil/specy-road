"""Argument parser for do-next-available-task (``do_next_task``)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from specy_road.git_workflow_config import ON_COMPLETE_MODES


def parse_do_next_task_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Pick the next actionable leaf task: sync integration branch, write brief, "
            "register on integration branch, create feature/rm-*, write prompt."
        ),
    )
    p.add_argument(
        "--base",
        default=None,
        metavar="BRANCH",
        help=(
            "Integration branch to sync before registering and branching "
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
    p.add_argument(
        "--interactive",
        action="store_true",
        help="Choose a task from a numbered list instead of auto-picking the first.",
    )
    p.add_argument(
        "--no-ci-skip-in-message",
        action="store_true",
        help=(
            "Omit CI skip tokens from the registration commit message "
            "(default appends common [skip ci] / [ci skip] / ***NO_CI*** markers)."
        ),
    )
    p.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        metavar="DIR",
        help="Repository root (default: git root or cwd).",
    )
    p.add_argument(
        "--on-complete",
        choices=sorted(ON_COMPLETE_MODES),
        default=None,
        metavar="MODE",
        help=(
            "Completion workflow for this task: pr, merge, or auto. "
            "Sets session for finish-this-task; skips TTY prompt when set. "
            "See roadmap/git-workflow.yaml on_complete and docs/git-workflow.md."
        ),
    )
    return p.parse_args(argv if argv is not None else sys.argv[1:])
