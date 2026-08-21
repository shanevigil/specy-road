"""Leaf-only pickup guards and empty-queue diagnostics for ``do_next_task``."""

from __future__ import annotations

import sys
from typing import Iterable

from do_next_available import _leaf_diagnostics, _leaf_node_ids
from specy_road.do_next_milestone_pickup import print_integration_branch_hint


def _fmt_ids(ids: Iterable[str], *, cap: int = 6) -> str:
    vals = list(ids)
    if not vals:
        return "none"
    if len(vals) <= cap:
        return ", ".join(vals)
    return ", ".join(vals[:cap]) + f", ... (+{len(vals) - cap} more)"


def assert_leaf_target(node: dict, nodes: list[dict]) -> None:
    if node["id"] in _leaf_node_ids(nodes):
        return
    print(
        f"error: selected node {node['id']!r} is not a leaf; "
        "default pickup can only claim leaves.",
        file=sys.stderr,
    )
    raise SystemExit(1)


def exit_no_actionable_leaves(
    nodes: list[dict], reg: dict, *, after_sync: bool,
    integration_branch: str | None = None,
) -> None:
    diag = _leaf_diagnostics(nodes, reg)
    phase = "after sync" if after_sync else "before sync"
    print(f"No actionable leaf tasks available ({phase}).", file=sys.stderr)
    print(
        "  Canonical model requires selecting an actionable leaf only.",
        file=sys.stderr,
    )
    print(
        "  leaf nodes: "
        f"{diag['leaf_nodes']} / total nodes: {diag['total_nodes']}",
        file=sys.stderr,
    )
    print(
        "  blocked by unmet dependencies: "
        f"{_fmt_ids(diag['deps_blocked_leaf_ids'])}",
        file=sys.stderr,
    )
    print(
        "  already claimed leaves: "
        f"{_fmt_ids(diag['claimed_leaf_ids'])}",
        file=sys.stderr,
    )
    print(
        "  open leaves (dependency-satisfied, unclaimed): "
        f"{_fmt_ids(diag['open_leaf_ids'])}",
        file=sys.stderr,
    )
    print(
        "  closed leaves (Complete/Cancelled): "
        f"{_fmt_ids(diag['closed_leaf_ids'])}",
        file=sys.stderr,
    )
    if diag["non_agentic_leaf_ids"]:
        print(
            "  non-agentic leaves: "
            f"{_fmt_ids(diag['non_agentic_leaf_ids'])}",
            file=sys.stderr,
        )
    if diag["missing_codename_leaf_ids"]:
        print(
            "  missing-codename leaves: "
            f"{_fmt_ids(diag['missing_codename_leaf_ids'])}",
            file=sys.stderr,
        )
    # Last, not first: the counts above explain the queue when they can, and
    # this covers the case they cannot show — a node that is not on the trunk
    # yet does not appear in any of them.
    print_integration_branch_hint(integration_branch)
    raise SystemExit(1)
