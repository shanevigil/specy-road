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


def _node_milestone_fields(
    n: dict, default_remote: str
) -> tuple[str, dict, str | None, str, str, str] | None:
    """Return ``(pid, me, state, remote, rollup_branch, integration_branch)`` or None to skip."""
    if not isinstance(n, dict):
        return None
    me = n.get("milestone_execution")
    if not isinstance(me, dict):
        return None
    pid = n.get("id")
    if not isinstance(pid, str):
        return None
    rb = me.get("rollup_branch")
    ib = me.get("integration_branch")
    if not isinstance(rb, str) or not isinstance(ib, str):
        return None
    rem = me.get("remote") or default_remote
    return pid, me, me.get("state"), rem, rb, ib


def _plan_closed_state(
    root: Path, pid: str, n: dict, *, rollup_ok: bool, apply: bool
) -> list[str]:
    if not rollup_ok or n.get("status") == "Complete":
        return []
    line = (
        f"sync parent {pid!r} status -> Complete "
        "(milestone_execution closed, rollup complete)"
    )
    if apply:
        edit_node_set_pairs(root, pid, [("status", "Complete")])
    return [line]


def _plan_open_state(
    root: Path,
    pid: str,
    *,
    state: str | None,
    remote: str,
    rollup_branch: str,
    integration_branch: str,
    rollup_ok: bool,
    fallback_head_delivery: bool,
    apply: bool,
) -> list[str]:
    out: list[str] = []
    merged = rollup_merged_into_integration(
        root,
        remote=remote,
        rollup_branch=rollup_branch,
        integration_branch=integration_branch,
    )
    delivery = merged is True or (fallback_head_delivery and rollup_ok)
    if delivery:
        if merged is None and fallback_head_delivery:
            out.append(
                f"note: {pid!r}: using --fallback-head-delivery "
                "(git merge proof unavailable)"
            )
        out.append(
            f"close milestone {pid!r}: set milestone_execution closed + status Complete"
        )
        if apply:
            patch_milestone_execution_state(root, pid, state="closed")
            edit_node_set_pairs(root, pid, [("status", "Complete")])
        return out

    if merged is False and rollup_ok:
        out.append(
            f"pending: {pid!r}: rollup complete but {rollup_branch!r} not merged "
            f"into {integration_branch!r} on {remote!r} "
            "(open MR via `specy-road open-milestone-pr`, merge, then re-run; "
            "or use --fallback-head-delivery if appropriate)."
        )
    elif merged is None and rollup_ok and not fallback_head_delivery:
        out.append(
            f"hint: {pid!r}: could not resolve {remote}/{rollup_branch} or "
            f"{remote}/{integration_branch} — git fetch {remote}, "
            "or use --fallback-head-delivery if work is already on integration."
        )

    if rollup_ok and state == "active":
        out.append(
            f"promote: {pid!r}: milestone_execution active -> pending_mr "
            "(all leaves complete)"
        )
        if apply:
            maybe_promote_milestone_to_pending_mr(
                root, pid, load_roadmap(root)["nodes"]
            )
    return out


def _plan_for_node(
    root: Path, n: dict, *, default_remote: str, args: argparse.Namespace
) -> list[str]:
    parsed = _node_milestone_fields(n, default_remote)
    if parsed is None:
        return []
    pid, _me, state, remote, rb, ib = parsed
    rollup_ok = n.get("rollup_status") == "Complete"
    if state == "closed":
        return _plan_closed_state(root, pid, n, rollup_ok=rollup_ok, apply=args.apply)
    return _plan_open_state(
        root,
        pid,
        state=state,
        remote=remote,
        rollup_branch=rb,
        integration_branch=ib,
        rollup_ok=rollup_ok,
        fallback_head_delivery=args.fallback_head_delivery,
        apply=args.apply,
    )


def _emit_planned(planned: list[str], *, apply: bool) -> None:
    if not planned:
        print("Nothing to reconcile (no milestone_execution rows needing action).")
        return
    for line in planned:
        print(line)
    if not apply:
        print("\n(dry-run: re-run with --apply to write changes)")
    else:
        print(
            "\n[ok] reconcile-milestone-status: applied changes "
            "(each step re-validated)."
        )


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    root = (args.repo_root or default_user_repo_root()).resolve()
    nodes = load_roadmap(root)["nodes"]
    _, default_remote, warns = resolve_integration_defaults(
        root, explicit_base=None, explicit_remote=None
    )
    for w in warns:
        print(f"warning: {w}", file=sys.stderr)

    planned: list[str] = []
    for n in nodes:
        planned.extend(
            _plan_for_node(root, n, default_remote=default_remote, args=args)
        )
    _emit_planned(planned, apply=args.apply)


if __name__ == "__main__":
    main()
