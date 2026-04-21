#!/usr/bin/env python3
"""Reconcile milestone parent ``status`` and ``milestone_execution`` with delivery policy."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from roadmap_crud_ops import edit_node_set_pairs
from roadmap_load import load_roadmap
from specy_road.git_milestone_delivery import rollup_merged_into_integration
from specy_road.git_workflow_config import resolve_integration_defaults
from specy_road.milestone_chunk_io import (
    maybe_promote_milestone_to_pending_mr,
    patch_milestone_execution_state,
)
from specy_road.runtime_paths import default_user_repo_root


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Milestone delivery: default is MR-first (rollup branch merged into "
            "integration on remote-tracking refs). With --fallback-head-delivery, "
            "treat rollup-complete parents as delivered when git cannot prove merge "
            "(e.g. local-only merges). Dry-run prints planned actions unless --apply."
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
        "--apply",
        action="store_true",
        help="Write chunk updates (otherwise print planned actions only).",
    )
    p.add_argument(
        "--fallback-head-delivery",
        action="store_true",
        help=(
            "When remote refs are missing or merge cannot be proven, still close "
            "milestones whose rollup_status is Complete (backup / integration-via-merge path)."
        ),
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    root = (args.repo_root or default_user_repo_root()).resolve()
    data = load_roadmap(root)
    nodes = data["nodes"]
    _, default_remote, warns = resolve_integration_defaults(
        root,
        explicit_base=None,
        explicit_remote=None,
    )
    for w in warns:
        print(f"warning: {w}", file=sys.stderr)

    planned: list[str] = []

    for n in nodes:
        if not isinstance(n, dict):
            continue
        me = n.get("milestone_execution")
        if not isinstance(me, dict):
            continue
        pid = n.get("id")
        if not isinstance(pid, str):
            continue
        st = me.get("state")
        rem = me.get("remote") or default_remote
        rb = me.get("rollup_branch")
        ib = me.get("integration_branch")
        if not isinstance(rb, str) or not isinstance(ib, str):
            continue

        rollup_ok = n.get("rollup_status") == "Complete"

        if st == "closed":
            if rollup_ok and n.get("status") != "Complete":
                planned.append(
                    f"sync parent {pid!r} status -> Complete (milestone_execution closed, rollup complete)",
                )
                if args.apply:
                    edit_node_set_pairs(root, pid, [("status", "Complete")])
            continue

        merged = rollup_merged_into_integration(
            root,
            remote=rem,
            rollup_branch=rb,
            integration_branch=ib,
        )
        delivery = False
        if merged is True:
            delivery = True
        elif args.fallback_head_delivery and rollup_ok:
            delivery = True
            if merged is None:
                planned.append(
                    f"note: {pid!r}: using --fallback-head-delivery (git merge proof unavailable)",
                )

        if delivery:
            planned.append(
                f"close milestone {pid!r}: set milestone_execution closed + status Complete",
            )
            if args.apply:
                patch_milestone_execution_state(root, pid, state="closed")
                edit_node_set_pairs(root, pid, [("status", "Complete")])
            continue

        if merged is False and rollup_ok:
            planned.append(
                f"pending: {pid!r}: rollup complete but {rb!r} not merged into {ib!r} on {rem!r} "
                f"(open MR via `specy-road open-milestone-pr`, merge, then re-run; "
                f"or use --fallback-head-delivery if appropriate).",
            )
        elif merged is None and rollup_ok and not args.fallback_head_delivery:
            planned.append(
                f"hint: {pid!r}: could not resolve {rem}/{rb} or {rem}/{ib} — git fetch {rem}, "
                f"or use --fallback-head-delivery if work is already on integration.",
            )

        if rollup_ok and st == "active":
            planned.append(
                f"promote: {pid!r}: milestone_execution active -> pending_mr (all leaves complete)",
            )
            if args.apply:
                maybe_promote_milestone_to_pending_mr(
                    root, pid, load_roadmap(root)["nodes"],
                )

    if not planned:
        print("Nothing to reconcile (no milestone_execution rows needing action).")
        return

    for line in planned:
        print(line)
    if not args.apply:
        print("\n(dry-run: re-run with --apply to write changes)")
    else:
        print("\n[ok] reconcile-milestone-status: applied changes (each step re-validated).")


if __name__ == "__main__":
    main()
