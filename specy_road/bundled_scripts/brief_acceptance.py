"""Render a node's ``goal`` and numbered ``acceptance`` criteria for the brief.

Used by :mod:`generate_brief` to add ``### Goal`` and ``### Acceptance
criteria`` under section 1 (execution target). Each criterion gets a stable id
``A1..An`` in list order; review records cite those ids for their
per-criterion result, so the numbering must not depend on anything but the
node's own ``acceptance`` list.

Public surface:

* :func:`acceptance_ids` — ``["A1", ...]`` for one node.
* :func:`render_goal_and_acceptance` — markdown lines ready to drop into the brief.
"""

from __future__ import annotations


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
