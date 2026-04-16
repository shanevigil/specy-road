"""Task queue selection for ``do_next_task`` (actionable leaves only).

Uses ``roadmap_gui_lib`` for registry/settings and ``roadmap_gui_remote`` for
``build_registry_enrichment`` / ``enrichment_is_mr_rejected`` so CLI ordering
matches the PM GUI’s forge enrichment rules.

Eligible-task order within each tier follows ``ordered_tree_rows`` (outline /
``sibling_order``), not merged JSON chunk list order.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from roadmap_gui_lib import load_registry, load_settings, registry_by_node_id
from roadmap_gui_remote import build_registry_enrichment, enrichment_is_mr_rejected
from roadmap_layout import effective_dependency_keys, ordered_tree_rows


def _claimed_node_ids(reg: dict) -> set[str]:
    return {e["node_id"] for e in reg.get("entries", []) if "node_id" in e}


def _statuses_by_node_key(nodes: list[dict]) -> dict[str, str]:
    """Map node_key -> lowercased status (dependencies reference node_key UUIDs)."""
    return {
        n["node_key"]: (n.get("status") or "").lower()
        for n in nodes
        if isinstance(n.get("node_key"), str) and n["node_key"]
    }


def _merge_status_overrides(
    nodes: list[dict],
    status_overrides: dict[str, str] | None,
) -> dict[str, str]:
    out = _statuses_by_node_key(nodes)
    if status_overrides:
        for k, v in status_overrides.items():
            out[k] = (v or "").lower()
    return out


def _unmet_effective_dependency_keys(
    node: dict,
    statuses_by_key: dict[str, str],
    effective_dep_keys: dict[str, set[str]],
) -> list[str]:
    nk = node.get("node_key")
    if not nk:
        return []
    return [
        d
        for d in effective_dep_keys.get(nk, set())
        if statuses_by_key.get(d, "") != "complete"
    ]


def interactive_deps_blocked_entries(
    nodes: list[dict],
    reg: dict,
    *,
    integration_statuses: dict[str, str],
    ready_ids: Iterable[str],
) -> list[tuple[dict, list[str]]]:
    """Leaves that look pickable except dependencies fail on integration-only statuses."""
    effective_dep_keys = effective_dependency_keys(nodes)
    ready_set = set(ready_ids)
    claimed = _claimed_node_ids(reg)
    leaf_ids = _leaf_node_ids(nodes)
    pairs: list[tuple[dict, list[str]]] = []
    for n in nodes:
        nid = n["id"]
        if nid not in leaf_ids or nid in ready_set:
            continue
        if not n.get("codename"):
            continue
        if not _agentic_execution_ok(n):
            continue
        if nid in claimed:
            continue
        stv = (n.get("status") or "Not Started").lower()
        if stv in ("complete", "cancelled", "in progress"):
            continue
        unmet = _unmet_effective_dependency_keys(
            n, integration_statuses, effective_dep_keys
        )
        if not unmet:
            continue
        pairs.append((n, unmet))
    order_index = _outline_order_index(nodes)
    tail = 10**9

    def sort_key(t: tuple[dict, list[str]]) -> int:
        return order_index.get(t[0]["id"], tail)

    pairs.sort(key=sort_key)
    return pairs


def _leaf_node_ids(nodes: list[dict]) -> set[str]:
    """Structural leaves: nodes that are not parents of any other node."""
    parent_ids = {
        n.get("parent_id")
        for n in nodes
        if isinstance(n.get("parent_id"), str) and n.get("parent_id")
    }
    return {n["id"] for n in nodes if n.get("id") not in parent_ids}


def _effective_deps_met(
    node: dict,
    statuses_by_key: dict[str, str],
    effective_dep_keys: dict[str, set[str]],
) -> bool:
    nk = node.get("node_key")
    if not nk:
        return True
    for dep in effective_dep_keys.get(nk, set()):
        if statuses_by_key.get(dep, "") != "complete":
            return False
    return True


def _agentic_execution_ok(n: dict) -> bool:
    exec_m = n.get("execution_milestone", "")
    exec_s = n.get("execution_subtask", "")
    return exec_m in ("Agentic-led", "Mixed") or exec_s == "agentic"


def _base_agentic_candidate(
    n: dict,
    statuses_by_key: dict[str, str],
    claimed: set[str],
    effective_dep_keys: dict[str, set[str]],
) -> bool:
    if n.get("type") == "gate":
        return False
    if not n.get("codename"):
        return False
    if not _agentic_execution_ok(n):
        return False
    if not _effective_deps_met(n, statuses_by_key, effective_dep_keys):
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


def _leaf_diagnostics(nodes: list[dict], reg: dict) -> dict[str, list[str] | int]:
    """Deterministic diagnostics when no actionable leaf exists."""
    effective_dep_keys = effective_dependency_keys(nodes)
    statuses_by_key = _statuses_by_node_key(nodes)
    claimed = _claimed_node_ids(reg)
    leaf_ids = _leaf_node_ids(nodes)
    order_index = _outline_order_index(nodes)

    leaf_nodes = [n for n in nodes if n.get("id") in leaf_ids]
    leaf_nodes = _sort_by_outline(leaf_nodes, order_index)

    claimed_leaf_ids: list[str] = []
    deps_blocked_leaf_ids: list[str] = []
    closed_leaf_ids: list[str] = []
    non_agentic_leaf_ids: list[str] = []
    missing_codename_leaf_ids: list[str] = []
    open_leaf_ids: list[str] = []

    for n in leaf_nodes:
        nid = n["id"]
        status = (n.get("status") or "Not Started").lower()
        if n.get("type") == "gate":
            non_agentic_leaf_ids.append(nid)
            continue
        if nid in claimed:
            claimed_leaf_ids.append(nid)
            continue
        if not n.get("codename"):
            missing_codename_leaf_ids.append(nid)
            continue
        if not _agentic_execution_ok(n):
            non_agentic_leaf_ids.append(nid)
            continue
        if not _effective_deps_met(n, statuses_by_key, effective_dep_keys):
            deps_blocked_leaf_ids.append(nid)
            continue
        if status in ("complete", "cancelled"):
            closed_leaf_ids.append(nid)
            continue
        open_leaf_ids.append(nid)

    return {
        "total_nodes": len(nodes),
        "leaf_nodes": len(leaf_nodes),
        "open_leaf_ids": open_leaf_ids,
        "claimed_leaf_ids": claimed_leaf_ids,
        "deps_blocked_leaf_ids": deps_blocked_leaf_ids,
        "closed_leaf_ids": closed_leaf_ids,
        "non_agentic_leaf_ids": non_agentic_leaf_ids,
        "missing_codename_leaf_ids": missing_codename_leaf_ids,
    }


def _collect_do_next_tiers(
    nodes: list[dict],
    base_ok,
    st,
    enr: dict[str, dict[str, Any]],
) -> tuple[list[dict], list[dict], list[dict]]:
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
    return blocked, mr_rejected, rest


def _available(
    nodes: list[dict],
    reg: dict,
    enrich: dict[str, dict[str, Any]] | None = None,
    *,
    status_overrides: dict[str, str] | None = None,
    virtual_complete_keys: set[str] | None = None,
) -> list[dict]:
    """Actionable leaf candidates: blocked first, then MR-rejected, then the rest.

    Within each tier, order follows outline (tree) order, not merged chunk order.

    ``status_overrides`` merges into per-node_key statuses for dependency checks only
    (e.g. feature-branch tips Complete before PR merges into the integration branch).

    ``virtual_complete_keys`` prefers leaves that depend on those keys within the
    non-blocked, non-MR-rejected tier (``rest``).
    """
    statuses_by_key = _merge_status_overrides(nodes, status_overrides)
    effective_dep_keys = effective_dependency_keys(nodes)
    claimed = _claimed_node_ids(reg)
    leaf_ids = _leaf_node_ids(nodes)
    enr = enrich or {}
    order_index = _outline_order_index(nodes)

    def st(node: dict) -> str:
        return (node.get("status") or "Not Started").lower()

    def base_ok(n: dict) -> bool:
        if n["id"] not in leaf_ids:
            return False
        return _base_agentic_candidate(
            n, statuses_by_key, claimed, effective_dep_keys
        )

    blocked, mr_rejected, rest = _collect_do_next_tiers(nodes, base_ok, st, enr)

    vc = virtual_complete_keys or set()
    rest_dep: list[dict] = []
    rest_other: list[dict] = []
    for n in rest:
        nk = n.get("node_key")
        deps = set(effective_dep_keys.get(nk, set())) if nk else set()
        if deps & vc:
            rest_dep.append(n)
        else:
            rest_other.append(n)

    return (
        _sort_by_outline(blocked, order_index)
        + _sort_by_outline(mr_rejected, order_index)
        + _sort_by_outline(rest_dep, order_index)
        + _sort_by_outline(rest_other, order_index)
    )
