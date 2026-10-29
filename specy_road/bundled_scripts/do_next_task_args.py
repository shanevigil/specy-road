"""Argument parser for do-next-available-task (``do_next_task``)."""

from __future__ import annotations

import argparse
import sys

from specy_road.git_workflow_config import ON_COMPLETE_MODES
from specy_road.runtime_paths import add_repo_root_arg


_DESCRIPTION = """\
Pick the next actionable leaf task: sync integration branch, write brief,
register on integration branch, create feature/rm-*, write prompt.

Selection order among eligible leaves:
  1. status Blocked   — a blocked leaf is the thing most worth unblocking, so
     it is offered FIRST rather than skipped. To keep work out of the queue
     entirely, give it a type: gate dependency; gates are never pickable and
     hold their dependents back.
  2. MR-rejected      — changes requested on the open PR/MR.
  3. everything else  — outline (tree) order.
With --prefer-agentic (or prefer_agentic_pick_order: true in
roadmap/git-workflow.yaml), each tier is ordered Agentic-led, Mixed, unset,
Human-led, outline order within each. The tiers and eligibility do not change.

A dependency on a phase or milestone is satisfied when that node's leaf
descendants are all Complete (the F-013 rollup), not when its own status field
says Complete.

execution_milestone (Human-led / Agentic-led / Mixed) is advisory metadata. It
does NOT gate pickup; --prefer-agentic only reorders.

A leaf whose planning sheet is still the scaffold-planning or brainstorm promote
placeholder, and whose node has no acceptance, is skipped with the reason
printed; --allow-unauthored picks it anyway.
"""


def _add_claim_visibility_args(p: argparse.ArgumentParser) -> None:
    """``--local`` and ``--owner``: who can see a claim, and who holds it (proposal §3.4)."""
    p.add_argument(
        "--local",
        action="store_true",
        help=(
            "Register the claim in this checkout only: no fetch, no merge, no push. "
            "The row is still committed on the integration branch locally, so finish, "
            "abort and the review gate work; push that branch when you want the team "
            "to see the claim. Peers cannot see a local claim until then."
        ),
    )
    p.add_argument(
        "--owner",
        default=None,
        metavar="NAME",
        help="Who holds the claim, written to the registry row (default: git config user.name).",
    )


def _add_pick_order_arg(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--prefer-agentic",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "Order each selection tier by execution_milestone: Agentic-led, Mixed, "
            "unset, Human-led (default: prefer_agentic_pick_order in "
            "roadmap/git-workflow.yaml, else off)."
        ),
    )


def parse_do_next_task_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=_DESCRIPTION,
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
        "--allow-unauthored",
        action="store_true",
        help=(
            "Also pick leaves whose planning sheet is still the scaffold-planning or "
            "brainstorm promote placeholder and whose node has no acceptance "
            "(skipped by default, with the reason printed)."
        ),
    )
    _add_pick_order_arg(p)
    _add_claim_visibility_args(p)
    add_repo_root_arg(p)
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
    p.add_argument(
        "--milestone-subtree",
        action="store_true",
        help=(
            "Limit pickup to leaves under the parent from work/.milestone-session.yaml "
            "(run specy-road start-milestone-session first)."
        ),
    )
    p.add_argument(
        "--under",
        default=None,
        metavar="NODE_ID",
        help=(
            "Limit pickup to leaves under this roadmap node (e.g. M7). Pass a parent id to scope to its whole subtree, or a single leaf id to target exactly that leaf — the scope includes the node itself. If work/.milestone-session.yaml exists, it must match this node."
        ),
    )
    return p.parse_args(argv if argv is not None else sys.argv[1:])
