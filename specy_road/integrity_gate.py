"""Turn test-integrity findings into review-gate problems (``policy.integrity_gate``).

With ``policy.integrity_gate: true`` in ``roadmap/orchestration.yaml``, every
``specy-road integrity`` finding for the commit under review is a gate problem
unless its exact line is in the node's ``planned_test_changes``. Both the switch
and the declarations are read from the integration branch (the ``ref``
:func:`review_policy_ref.policy_source` returns), never from the leaf branch or
the working tree: the leaf approved before pickup is the waiver, and an executor
cannot add a declaration from its worktree.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from specy_road.bundled_scripts.roadmap_load_at_ref import load_roadmap_nodes_at_ref
from specy_road.git_subprocess import git_text
from specy_road.integrity import compare_integrity


def planned_test_changes(repo_root: Path, ref: str, node_id: str) -> set[str]:
    """The node's ``planned_test_changes`` as committed on ``ref``; empty when unreadable or absent."""
    nodes = load_roadmap_nodes_at_ref(repo_root, ref) or []
    node = next((n for n in nodes if n.get("id") == node_id), None) or {}
    return {s for s in node.get("planned_test_changes") or [] if isinstance(s, str)}


def integrity_gate_problems(
    repo_root: Path, policy: dict[str, Any], node_id: str, commit: str | None, ref: str | None
) -> list[str]:
    """One problem per finding for ``commit`` that ``node_id`` did not declare on ``ref``.

    Nothing when the policy is off or there is no commit to judge; a missing
    integration ref or merge base is itself a problem, so the gate fails closed.
    """
    if not policy.get("integrity_gate") or not commit:
        return []
    base = git_text(["merge-base", ref, commit], repo_root) if ref else None
    if not base:
        return [f"integrity gate: no merge base between the integration branch ({ref}) and {commit}"]
    findings = compare_integrity(repo_root, base, commit)
    if not findings:
        return []
    declared = planned_test_changes(repo_root, ref, node_id)
    return [
        f"integrity (undeclared): {line} — not in {node_id}'s planned_test_changes on {ref}"
        for line in (f.line() for f in findings)
        if line not in declared
    ]
