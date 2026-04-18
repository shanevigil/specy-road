#!/usr/bin/env python3
"""Print gh pr / glab hints for one PR: milestone rollup → integration branch."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from roadmap_load import load_roadmap
from specy_road.git_workflow_config import (
    merge_request_requires_manual_approval,
    resolve_integration_defaults,
)
from specy_road.milestone_session import (
    milestone_session_path,
    read_milestone_session,
)
from specy_road.runtime_paths import default_user_repo_root


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Show commands to open a single PR/MR from "
            "feature/rm-<milestone-codename> to the integration branch "
            "(after subtree work is complete)."
        ),
    )
    p.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        metavar="DIR",
        help="Repository root (default: git root or cwd).",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    root = (args.repo_root or default_user_repo_root()).resolve()
    ms = read_milestone_session(milestone_session_path(root / "work"))
    if not ms:
        print(
            "error: work/.milestone-session.yaml not found — run "
            "`specy-road start-milestone-session <PARENT_NODE_ID>` first.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    ib, gw_remote, _gw = resolve_integration_defaults(
        root,
        explicit_base=None,
        explicit_remote=None,
    )
    if ms.integration_branch != ib:
        print(
            "warning: session records integration branch "
            f"{ms.integration_branch!r} but resolved default is {ib!r} "
            f"— using {ib!r} for --base.",
            file=sys.stderr,
        )

    nodes = load_roadmap(root)["nodes"]
    by_id = {n["id"]: n for n in nodes if n.get("id")}
    parent = by_id.get(ms.parent_node_id)
    title = (
        f"[{ms.parent_node_id}] {parent.get('title', '').strip()}"
        if parent
        else f"Milestone {ms.parent_node_id}"
    )

    mr_manual = merge_request_requires_manual_approval(root)

    print()
    print("Open one PR/MR from the rollup branch to integration:")
    print(
        f'  gh pr create --base {ib} --head {ms.rollup_branch} '
        f'--title {title!r}'
    )
    print("  (GitLab: `glab mr create` or the web UI — same idea.)")
    print(f"  Remote: {gw_remote!r}")
    if mr_manual:
        print(
            "  Merge requests require manual approval — wait for review, "
            "then merge."
        )
    print()


if __name__ == "__main__":
    main()
