"""Render a node's ``goal`` and numbered ``acceptance`` criteria for the brief.

Used by :mod:`generate_brief` to add ``### Goal`` and ``### Acceptance
criteria`` under section 1 (execution target). Each criterion gets a stable id
``A1..An`` in list order; review records cite those ids for their
per-criterion result, so the numbering must not depend on anything but the
node's own ``acceptance`` list.

Public surface:

* :func:`acceptance_ids` — ``["A1", ...]`` for one node.
* :func:`render_goal_and_acceptance` — markdown lines ready to drop into the brief.
* :func:`warn_acceptance_missing` — ``validate``'s warning for leaves a review
  cannot attest per criterion.
* :func:`warn_acceptance_merged` — ``validate``'s warning for a criterion that
  looks like several joined with ``|``.
"""

from __future__ import annotations

import sys

from specy_road.milestone_subtree import structural_leaf_ids
from specy_road.node_kinds import is_pickable

_WARN_CAP = 10


def _acceptance(node: dict) -> list[str]:
    raw = node.get("acceptance") or []
    return [a for a in raw if isinstance(a, str) and a.strip()]


def acceptance_ids(node: dict) -> list[str]:
    """Stable ids for the node's acceptance criteria, in list order."""
    return [f"A{i}" for i in range(1, len(_acceptance(node)) + 1)]


def render_goal_and_acceptance(node: dict) -> list[str]:
    goal = (node.get("goal") or "").strip()
    out = ["### Goal", "", goal if goal else "_(no `goal` set on this node)_", ""]
    out += ["### Acceptance criteria", ""]
    items = _acceptance(node)
    if not items:
        out.append(
            "_(no `acceptance` set on this node — reviewers judge against the "
            "planning sheet instead)_"
        )
    for aid, text in zip(acceptance_ids(node), items):
        out.append(f"- **{aid}:** {text.strip()}")
    out.append("")
    return out


def warn_acceptance_missing(nodes: list[dict], gate_on: bool) -> None:
    """Warn (stderr only) on open actionable leaves without ``acceptance`` while the gate is on.

    Their review records need no per-criterion result, so a review attests
    nothing criterion by criterion. Without the gate the field is optional.
    """
    if not gate_on:
        return
    leaves = structural_leaf_ids(nodes)
    bare = [n["id"] for n in nodes
            if n.get("id") in leaves and is_pickable(n)
            and n.get("status") != "Complete" and not _acceptance(n)]
    for nid in bare[:_WARN_CAP]:
        print(f"warning: {nid} has no acceptance criteria; with require_implementation_review_before_finish "
              "on, a review of it cannot attest per-criterion results "
              f"(set acceptance with: specy-road edit-node {nid} --set acceptance=..., one --set per criterion)",
              file=sys.stderr)
    if len(bare) > _WARN_CAP:
        print(f"warning: … and {len(bare) - _WARN_CAP} more leaves without acceptance criteria", file=sys.stderr)


def warn_acceptance_merged(nodes: list[dict]) -> None:
    """Warn (stderr only) on an open node whose criterion contains ``|``.

    ``edit-node --set acceptance=a|b`` stores one criterion, and a review then
    attests ``A1`` for both. 0.3.1rc1 adopters wrote lists that way because
    nothing said otherwise.
    """
    merged = [n["id"] for n in nodes
              if n.get("status") != "Complete" and any("|" in a for a in _acceptance(n))]
    for nid in merged[:_WARN_CAP]:
        print(f"warning: {nid} has an acceptance criterion containing '|'; if that is several criteria, "
              f"re-set them with one --set per criterion: specy-road edit-node {nid} "
              "--set acceptance='First' --set acceptance='Second'", file=sys.stderr)
    if len(merged) > _WARN_CAP:
        print(f"warning: … and {len(merged) - _WARN_CAP} more nodes with '|' in a criterion", file=sys.stderr)
