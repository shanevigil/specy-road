"""Milestone subtree flags for do-next-available-task (session + --under)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from specy_road.milestone_session import (
    milestone_session_path,
    read_milestone_session,
)


def resolve_milestone_parent_filter(
    work_dir: Path,
    args: argparse.Namespace,
) -> str | None:
    """Return parent node id for subtree filter, or None. May sys.exit on conflict."""
    ms = read_milestone_session(milestone_session_path(work_dir))
    parent = args.under
    if args.milestone_subtree:
        if not ms:
            print(
                "error: work/.milestone-session.yaml not found — run "
                "`specy-road start-milestone-session <PARENT_NODE_ID>` first.",
                file=sys.stderr,
            )
            raise SystemExit(1)
        if parent and parent != ms.parent_node_id:
            print(
                "error: --under "
                f"{parent!r} does not match milestone session parent "
                f"{ms.parent_node_id!r}.",
                file=sys.stderr,
            )
            raise SystemExit(1)
        return ms.parent_node_id
    if parent:
        if ms and ms.parent_node_id != parent:
            print(
                "error: --under "
                f"{parent!r} does not match work/.milestone-session.yaml parent "
                f"{ms.parent_node_id!r}.",
                file=sys.stderr,
            )
            raise SystemExit(1)
        return parent
    return None


def exit_no_leaves_under_parent(parent_id: str, *, after_sync: bool) -> None:
    phase = "after sync" if after_sync else "before sync"
    print(
        f"No actionable leaf tasks under parent {parent_id!r} ({phase}).",
        file=sys.stderr,
    )
    print(
        "  Try another parent, finish in-progress work, or clear "
        "dependencies.",
        file=sys.stderr,
    )
    raise SystemExit(1)
