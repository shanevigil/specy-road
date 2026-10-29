"""Argument parser for ``specy-road finish-this-task``."""

from __future__ import annotations

import argparse

from specy_road.git_workflow_config import ON_COMPLETE_MODES
from specy_road.runtime_paths import add_repo_root_arg

_DESCRIPTION = (
    "Mark the current roadmap task complete, validate, export, digest, commit.\n"
    "\n"
    "Finishing the last open leaf under a parent also flips that parent "
    "to Complete, in the same bookkeeping commit, walking up as far as "
    "the rollup reaches. Nothing is printed when there is nothing to "
    "close, so a run that leaves other leaves open looks the same as "
    "one with no parents to close.\n"
    "\n"
    "The exception is a node carrying a milestone_execution block "
    "(written by start-milestone-session): its status belongs to the "
    "milestone-rollup state machine, which closes it only once the "
    "rollup branch is proven merged. Use "
    "specy-road reconcile-milestone-status for those.\n"
    "\n"
    "--on-complete merge (and auto when merge succeeds) lands on the "
    "integration branch and pushes it. --push only pushes the feature "
    "branch; it does not open the PR. The printed gh/glab command is pasteable."
)


def _add_landing_args(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--push",
        action="store_true",
        help=(
            "After the bookkeeping commit, run git push -u <remote> <branch>. "
            "Does not open the PR — the gh/glab line is printed for you."
        ),
    )
    p.add_argument(
        "--remote",
        default="origin",
        metavar="NAME",
        help="Remote for --push (default: origin).",
    )
    p.add_argument(
        "--on-complete",
        choices=sorted(ON_COMPLETE_MODES),
        default=None,
        metavar="MODE",
        help=(
            "Override completion workflow: pr, merge, or auto. "
            "merge lands on the integration branch and pushes it. "
            "Default: session file from do-next-available-task, then "
            "roadmap/git-workflow.yaml / SPECY_ROAD_ON_COMPLETE."
        ),
    )
    p.add_argument(
        "--delete-branch",
        action="store_true",
        help=(
            "Once the merge lands on the integration branch (merge, or auto "
            "when its merge succeeds), delete the feature branch locally and "
            "on the remote. Refused under pr: there the branch is the only "
            "copy of the work until the PR merges."
        ),
    )


def parse_finish_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=_DESCRIPTION,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _add_landing_args(p)
    add_repo_root_arg(p)
    p.add_argument(
        "--no-cleanup-work",
        action="store_true",
        help=(
            "Keep work/brief-, work/prompt-, and work/implementation-summary- for this node "
            "(default: delete after successful validate/export/digest)."
        ),
    )
    p.add_argument(
        "--allow-empty-implementation",
        action="store_true",
        help=(
            "Finish even though the branch changes no file under the node's "
            "declared touch zones. For a leaf that genuinely needs no code "
            "change; otherwise fix the zones or abort the pickup."
        ),
    )
    p.add_argument(
        "--allow-scaffold-planning",
        action="store_true",
        help=(
            "Finish even though the node's planning sheet still has the "
            "scaffold-planning or brainstorm promote placeholder text. "
            "Otherwise write the sheet and commit it on this branch."
        ),
    )
    p.add_argument(
        "--no-milestone-rollup",
        action="store_true",
        help=(
            "Skip milestone dual-land (cherry-pick bookkeeping to integration + merge "
            "leaf into rollup) when work/.milestone-session.yaml exists; use normal "
            "on_complete instead."
        ),
    )
    return p.parse_args(argv)
