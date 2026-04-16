"""Task queue selection for ``do_next_task`` (blocked and MR-rejected first).

Uses ``roadmap_gui_lib`` for registry/settings and ``roadmap_gui_remote`` for
``build_registry_enrichment`` / ``enrichment_is_mr_rejected`` so CLI ordering
matches the PM GUI’s forge enrichment rules.

Eligible-task order within each tier follows ``ordered_tree_rows`` (outline /
``sibling_order``), not merged JSON chunk list order.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from roadmap_gui_lib import load_registry, load_settings, registry_by_node_id
from roadmap_gui_remote import build_registry_enrichment, enrichment_is_mr_rejected
from roadmap_layout import ordered_tree_rows


def _claimed_node_ids(reg: dict) -> set[str]:
    return {e["node_id"] for e in reg.get("entries", []) if "node_id" in e}


def _statuses_by_node_key(nodes: list[dict]) -> dict[str, str]:
    """Map node_key -> lowercased status (dependencies reference node_key UUIDs)."""
    return {
        n["node_key"]: (n.get("status") or "").lower()
        for n in nodes
        if isinstance(n.get("node_key"), str) and n["node_key"]
    }


def _deps_met(node: dict, statuses_by_key: dict[str, str]) -> bool:
    return all(
        statuses_by_key.get(dep, "") == "complete"
        for dep in (node.get("dependencies") or [])
    )


def _agentic_execution_ok(n: dict) -> bool:
    exec_m = n.get("execution_milestone", "")
    exec_s = n.get("execution_subtask", "")
    return exec_m in ("Agentic-led", "Mixed") or exec_s == "agentic"


def _base_agentic_candidate(
    n: dict,
    statuses_by_key: dict[str, str],
    claimed: set[str],
) -> bool:
    if not n.get("codename"):
        return False
    if not _agentic_execution_ok(n):
        return False
    if not _deps_met(n, statuses_by_key):
        return False
    if n["id"] in claimed:
        return False
    return True


def _outline_order_index(nodes: list[dict]) -> dict[str, int]:
    """Pre-order outline index: siblings ordered by (sibling_order, id)."""
    rows = ordered_tree_rows(nodes)
    return {row[0]["id"]: i for i, row in enumerate(rows)}


def _sort_by_outline(
    items: list[dict], order_index: dict[str, int]
) -> list[dict]:
    tail = 10**9

    def key(n: dict) -> int:
        return order_index.get(n["id"], tail)

    return sorted(items, key=key)


def _load_branch_enrichment(root: Path) -> dict[str, dict[str, Any]]:
    """Same enrichment as the PM GUI when settings/registry load; `{}` on any failure (offline-safe)."""
    try:
        reg = load_registry(root)
        by_reg = registry_by_node_id(reg)
        settings = load_settings(root)
        gr = settings.get("git_remote") or {}
        return build_registry_enrichment(by_reg, gr, repo_root=root, remote="origin")
    except (OSError, RuntimeError, KeyError, TypeError, ValueError):
        return {}


def _available(
    nodes: list[dict],
    reg: dict,
    enrich: dict[str, dict[str, Any]] | None = None,
) -> list[dict]:
    """Agentic candidates: blocked first, then MR-rejected (per `enrich`), then the rest.

    Within each tier, order follows outline (tree) order, not merged chunk order.
    """
    statuses_by_key = _statuses_by_node_key(nodes)
    claimed = _claimed_node_ids(reg)
    enr = enrich or {}
    order_index = _outline_order_index(nodes)

    def st(node: dict) -> str:
        return (node.get("status") or "Not Started").lower()

    def base_ok(n: dict) -> bool:
        return _base_agentic_candidate(n, statuses_by_key, claimed)

    blocked: list[dict] = []
    seen: set[str] = set()

    for n in nodes:
        if not base_ok(n):
            continue
        if st(n) == "blocked":
            blocked.append(n)
            seen.add(n["id"])

    mr_rejected: list[dict] = []
    for n in nodes:
        if n["id"] in seen or not base_ok(n):
            continue
        if st(n) in ("complete", "cancelled"):
            continue
        if enrichment_is_mr_rejected(enr.get(n["id"])):
            mr_rejected.append(n)
            seen.add(n["id"])

    rest: list[dict] = []
    skip_rest = {"complete", "in progress", "cancelled", "blocked"}
    for n in nodes:
        if n["id"] in seen:
            continue
        if not base_ok(n):
            continue
        if st(n) in skip_rest:
            continue
        rest.append(n)

    return (
        _sort_by_outline(blocked, order_index)
        + _sort_by_outline(mr_rejected, order_index)
        + _sort_by_outline(rest, order_index)
    )
