"""Roadmap read-only and governance API routes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from roadmap_gui_lib import (
    load_registry,
    load_settings,
    registry_by_node_id,
    repo_settings_id,
)
from roadmap_gui_remote import build_pr_hints, build_registry_enrichment
from roadmap_gui_tree import can_indent_outline, can_outdent_outline
from roadmap_layout import (
    compute_dependency_steps,
    dependency_edges_detailed,
    dependency_inheritance_display,
    ordered_tree_rows,
)
from roadmap_load import load_roadmap

from specy_road.git_workflow_config import build_git_workflow_status
from specy_road.pm_gui_fingerprint import (
    outline_mutation_fingerprint,
    pm_gui_mutation_fingerprint,
)
from specy_road.registry_remote_overlay import (
    describe_integration_branch_auto_ff,
    last_registry_auto_fetch_status,
    merge_registry_with_remote_overlay,
    maybe_auto_git_fetch,
    maybe_auto_integration_ff,
    registry_remote_overlay_enabled,
    resolve_git_remote,
)
from specy_road.governance_completion import (
    constitution_needs_completion,
    vision_needs_completion,
)

from specy_road.gui_app_helpers import get_repo_root


def _apply_rollup_on_wire(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    F-013: single source of truth for rollup status.

    ``load_roadmap`` attaches ``rollup_status`` to every node. For the GUI wire
    payload, substitute each node's ``status`` with its ``rollup_status`` so
    the UI never shows a parent as "Not Started" while its leaves are all
    "Complete". Leaves are unchanged (rollup == own status). Keeps both
    fields on the wire so new UI code can be explicit if it wants.
    """
    out: list[dict[str, Any]] = []
    for n in nodes:
        copy = dict(n)
        rs = copy.get("rollup_status")
        if isinstance(rs, str) and rs:
            copy["status"] = rs
        out.append(copy)
    return out


def _outline_actions_for(nodes: list[dict[str, Any]]) -> dict[str, dict[str, bool]]:
    by_id = {n["id"]: n for n in nodes}
    return {
        n["id"]: {
            "can_indent": can_indent_outline(nodes, by_id, n["id"]),
            "can_outdent": can_outdent_outline(by_id, n["id"]),
        }
        for n in nodes
    }


def _stringified_fingerprints(root: Path) -> dict[str, str]:
    """Both fingerprints, JSON-string encoded.

    ``fingerprint`` is the **narrow** outline token sent back as
    ``X-PM-Gui-Fingerprint`` on mutating POSTs. ``view_fingerprint`` is
    the broader change-detection token used by the polling refresh hook.
    Both are emitted as strings: the underlying integer routinely exceeds
    ``2**53`` and would lose precision when round-tripped through the
    browser's IEEE 754 ``Number`` type, producing spurious 412s.
    """
    return {
        "fingerprint": str(outline_mutation_fingerprint(root)),
        "view_fingerprint": str(pm_gui_mutation_fingerprint(root)),
    }


def _roadmap_payload(root: Path, doc: dict[str, Any]) -> dict[str, Any]:
    """Assemble the ``GET /api/roadmap`` JSON body (``doc`` from ``load_roadmap``)."""
    nodes = _apply_rollup_on_wire(doc.get("nodes") or [])
    head_reg = load_registry(root)
    reg = head_reg
    registry_overlay_meta: dict[str, Any] | None = None
    if registry_remote_overlay_enabled(root):
        maybe_auto_git_fetch(root, resolve_git_remote(root))
        reg, registry_overlay_meta = merge_registry_with_remote_overlay(
            head_reg, root
        )
    by_reg = registry_by_node_id(reg)
    settings = load_settings(root)
    gr = settings.get("git_remote") or {}
    pr_hints = build_pr_hints(by_reg, gr)
    gw = build_git_workflow_status(root)
    resolved = gw.get("resolved") or {}
    rm_raw = resolved.get("remote")
    rm = str(rm_raw).strip() if isinstance(rm_raw, str) and rm_raw.strip() else "origin"
    git_enrichment = build_registry_enrichment(
        by_reg, gr, repo_root=root, remote=rm
    )
    tree_rows = ordered_tree_rows(nodes)
    ordered = [t[0] for t in tree_rows]
    row_depths = [d for _, d in tree_rows]
    dep_starts, dep_spans = compute_dependency_steps(nodes)
    edges = dependency_edges_detailed(nodes)
    dep_inheritance = dependency_inheritance_display(nodes)
    out: dict[str, Any] = {
        "version": doc.get("version"),
        "nodes": nodes,
        "registry": reg,
        "registry_by_node": by_reg,
        "tree": [
            {"id": n["id"], "outline_depth": d, "row_index": i}
            for i, (n, d) in enumerate(tree_rows)
        ],
        "dependency_depths": dep_starts,
        "dependency_spans": dep_spans,
        "edges": edges,
        "ordered_ids": [n["id"] for n in ordered],
        "row_depths": row_depths,
        "pr_hints": pr_hints,
        "git_enrichment": git_enrichment,
        "dependency_inheritance": dep_inheritance,
        "outline_actions": _outline_actions_for(nodes),
        "git_workflow": gw,
    }
    if registry_overlay_meta is not None:
        fetch_status = last_registry_auto_fetch_status(root)
        if fetch_status is not None:
            registry_overlay_meta = dict(registry_overlay_meta)
            registry_overlay_meta["last_auto_fetch_attempt"] = fetch_status
        out["registry_overlay"] = registry_overlay_meta
    ibaff = describe_integration_branch_auto_ff(root)
    if ibaff.get("enabled") is True:
        out["integration_branch_auto_ff"] = ibaff
    out.update(_stringified_fingerprints(root))
    return out


def _pm_gui_finalize_state(root: Path) -> None:
    """Run the GET-side background sync (auto-fetch + auto-FF).

    Callers (``GET /api/roadmap`` and ``GET /api/roadmap/fingerprint``)
    must invoke this *before* computing the fingerprints they hand back
    to the client, so the values they emit reflect any HEAD/refs
    movement caused by the background sync.
    """
    if registry_remote_overlay_enabled(root):
        maybe_auto_git_fetch(root, resolve_git_remote(root))
    maybe_auto_integration_ff(root)


def register_core(api: APIRouter) -> None:
    @api.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @api.get("/repo")
    def api_repo() -> dict[str, str]:
        r = get_repo_root()
        return {"repo_root": str(r), "repo_id": repo_settings_id(r)}

    @api.get("/roadmap")
    def api_roadmap() -> dict[str, Any]:
        root = get_repo_root()
        # Run auto-fetch/auto-FF before reading the roadmap; both
        # fingerprints baked into the payload by ``_roadmap_payload``
        # will reflect any HEAD/refs movement caused by these side
        # effects.
        _pm_gui_finalize_state(root)
        try:
            doc = load_roadmap(root)
        except (OSError, SystemExit, ValueError) as e:
            raise HTTPException(status_code=500, detail=str(e)) from e
        return _roadmap_payload(root, doc)

    @api.get("/roadmap/fingerprint")
    def api_roadmap_fingerprint() -> dict[str, str]:
        root = get_repo_root()
        # Run the same auto-fetch / auto-FF the GET /roadmap endpoint runs
        # so the polling refresh hook sees a coherent token.
        _pm_gui_finalize_state(root)
        return _stringified_fingerprints(root)

    @api.get("/governance-completion")
    def api_governance_completion() -> dict[str, bool]:
        root = get_repo_root()
        return {
            "vision_needs_completion": vision_needs_completion(root),
            "constitution_needs_completion": constitution_needs_completion(root),
        }

    @api.get("/git-workflow-status")
    def api_git_workflow_status() -> dict[str, Any]:
        root = get_repo_root()
        return build_git_workflow_status(root)
