"""Argument parser for ``specy-road grind-session``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from specy_road.git_workflow_config import ON_COMPLETE_MODES


def _add_mode_and_stop_args(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--plan", "--dry-run", dest="plan", action="store_true",
        help=(
            "Read-only: print the session plan (ready/blocked/active + dependency "
            "waves + parallel batches) and exit 0. No git, no pickup."
        ),
    )
    p.add_argument("--until", default=None, metavar="NODE_ID",
                   help="Stop after successfully finishing this node id (inclusive).")
    p.add_argument("--under", default=None, metavar="PARENT_NODE_ID",
                   help="Only pick leaves under this roadmap parent subtree (e.g. M7).")
    p.add_argument("--max-leaves", type=int, default=None, metavar="N",
                   help="Stop after N successful finish cycles.")
    p.add_argument("--max-cycles", type=int, default=100, metavar="N",
                   help="Safety bound on total loop iterations (default 100).")


def _add_implement_args(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--implement-mode", choices=("manual", "hook"), default="manual",
        help=(
            "manual (default): after pickup, wait for a ready signal (file or Enter) "
            "while you/your agent implement; hook: run --implement-cmd per cycle."
        ),
    )
    p.add_argument(
        "--implement-cmd", default=None, metavar="CMD",
        help=(
            "Shell command to run for implementation in hook mode (env: SPECY_ROAD_NODE_ID, "
            "SPECY_ROAD_BRANCH, SPECY_ROAD_BRIEF, SPECY_ROAD_PROMPT, SPECY_ROAD_REPO_ROOT)."
        ),
    )
    p.add_argument(
        "--ready-signal", default="work/.session-ready", metavar="PATH",
        help=(
            "manual mode: path (relative to repo root) whose creation signals "
            "implementation is done (default work/.session-ready). Enter also works on a TTY."
        ),
    )
    p.add_argument("--signal-timeout", type=float, default=0.0, metavar="SECONDS",
                   help="manual mode: max seconds to wait for the ready signal (0 = forever).")
    p.add_argument(
        "--pre-finish-cmd", default=None, metavar="CMD",
        help=(
            "Shell command run after implement, before finish-this-task (e.g. "
            "'make test && specy-road validate'). Non-zero stops the session (exit 4)."
        ),
    )


def _add_passthrough_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--repo-root", type=Path, default=None, metavar="DIR",
                   help="Repository root (default: git root or cwd).")
    p.add_argument("--base", default=None, metavar="BRANCH",
                   help="Integration branch (default: roadmap/git-workflow.yaml).")
    p.add_argument("--remote", default=None, metavar="NAME",
                   help="Git remote (default: roadmap/git-workflow.yaml).")
    p.add_argument("--on-complete", choices=sorted(ON_COMPLETE_MODES), default=None,
                   metavar="MODE",
                   help="Completion workflow per leaf: pr|merge|auto. Loop needs merge/auto.")
    p.add_argument("--no-ci-skip-in-message", action="store_true",
                   help="Pass through to pickup registration commit.")
    p.add_argument("--milestone-subtree", action="store_true",
                   help="Pass through to pickup (uses work/.milestone-session.yaml).")
    p.add_argument("--push", action="store_true",
                   help="Pass --push through to finish-this-task.")
    p.add_argument("--json", action="store_true",
                   help="Emit one JSON event per line (picked/finished/blocked/stopped/...).")


def parse_grind_session_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="specy-road grind-session",
        description=(
            "Orchestrate the task loop: do-next-available-task -> implement -> "
            "(optional pre-finish hook) -> finish-this-task, repeated until a stop "
            "condition. Use --plan for a read-only dependency/wave report (no git)."
        ),
    )
    _add_mode_and_stop_args(p)
    _add_implement_args(p)
    _add_passthrough_args(p)
    ns = p.parse_args(argv if argv is not None else sys.argv[1:])
    if ns.implement_mode == "hook" and not ns.implement_cmd and not ns.plan:
        p.error("--implement-mode hook requires --implement-cmd")
    return ns
