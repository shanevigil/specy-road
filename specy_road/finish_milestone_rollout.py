"""Milestone rollup path after finish-this-task bookkeeping."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from specy_road.milestone_rollup_git import (
    cherry_pick_bookkeeping_to_integration,
    merge_leaf_into_rollup,
    push_branch,
    rev_parse_head,
)
from specy_road.milestone_session import MilestoneSession, milestone_session_path, read_milestone_session
from specy_road.milestone_subtree import subtree_node_ids
from specy_road.on_complete_session import remove_on_complete_session


def milestone_session_conflict_or_exit(
    ms: MilestoneSession | None,
    *,
    no_milestone_rollup: bool,
    node_id: str,
    nodes: list[dict],
) -> None:
    if ms is None or no_milestone_rollup:
        return
    if node_id in subtree_node_ids(ms.parent_node_id, nodes):
        return
    print(
        "error: work/.milestone-session.yaml is for parent "
        f"{ms.parent_node_id!r}, but this task ({node_id!r}) is not in that subtree.",
        file=sys.stderr,
    )
    print(
        "  Use `specy-road finish-this-task --no-milestone-rollup`, or remove the "
        "session file, or finish a leaf under the milestone parent.",
        file=sys.stderr,
    )
    raise SystemExit(1)


def try_milestone_rollup_finish(
    repo: Path,
    args: argparse.Namespace,
    *,
    work_dir: Path,
    node_id: str,
    nodes: list[dict],
    branch: str,
    sess_path: Path,
    ib: str,
    gw_remote: str,
) -> bool:
    """
    If milestone session applies, push leaf, cherry-pick bookkeeping to integration,
    merge leaf into rollup. Returns True if this path handled completion (caller skips
    apply_on_complete_mode).
    """
    ms = read_milestone_session(milestone_session_path(work_dir))
    milestone_session_conflict_or_exit(
        ms,
        no_milestone_rollup=args.no_milestone_rollup,
        node_id=node_id,
        nodes=nodes,
    )
    if ms is None or args.no_milestone_rollup:
        return False
    if node_id not in subtree_node_ids(ms.parent_node_id, nodes):
        return False

    bookkeeping_sha = rev_parse_head(repo)
    print("\n[milestone] pushing leaf branch, then landing bookkeeping on integration …")
    ok, err = push_branch(repo, gw_remote, branch)
    if not ok:
        print(f"error: {err}", file=sys.stderr)
        raise SystemExit(1)
    ok, err = cherry_pick_bookkeeping_to_integration(
        repo,
        remote=gw_remote,
        integration_branch=ib,
        bookkeeping_commit=bookkeeping_sha,
        leaf_branch=branch,
    )
    if not ok:
        print(f"error: {err}", file=sys.stderr)
        raise SystemExit(1)
    print(f"[milestone] merging {branch} into {ms.rollup_branch} …")
    ok, err = merge_leaf_into_rollup(
        repo,
        remote=gw_remote,
        rollup_branch=ms.rollup_branch,
        leaf_branch=branch,
        integration_branch=ib,
    )
    if not ok:
        print(f"error: {err}", file=sys.stderr)
        raise SystemExit(1)
    remove_on_complete_session(sess_path)
    print("\n[ok] Milestone rollup: integration branch updated; rollup branch merged.")
    print(f"     You are on {ib!r}. Next: specy-road do-next-available-task --milestone-subtree")
    print("     When the subtree is done: specy-road open-milestone-pr")
    return True
