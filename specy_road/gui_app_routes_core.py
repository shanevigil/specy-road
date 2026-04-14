"""Roadmap read-only and governance API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from roadmap_gui_lib import (
    load_registry,
    load_settings,
    registry_by_node_id,
    roadmap_fingerprint,
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
from specy_road.governance_completion import (
    constitution_needs_completion,
    vision_needs_completion,
)

from specy_road.gui_app_helpers import get_repo_root


def register_core(api: APIRouter) -> None:
    @api.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @api.get("/repo")
    def api_repo() -> dict[str, str]:
        r = get_repo_root()
        return {"repo_root": str(r)}

    @api.get("/roadmap")
    def api_roadmap() -> dict[str, Any]:
        root = get_repo_root()
        try:
            doc = load_roadmap(root)
        except (OSError, SystemExit, ValueError) as e:
            raise HTTPException(status_code=500, detail=str(e)) from e
        nodes = doc.get("nodes") or []
        reg = load_registry(root)
        by_reg = registry_by_node_id(reg)
        settings = load_settings(root)
        gr = settings.get("git_remote") or {}
        pr_hints = build_pr_hints(by_reg, gr)
        git_enrichment = build_registry_enrichment(by_reg, gr)
        tree_rows = ordered_tree_rows(nodes)
        ordered = [t[0] for t in tree_rows]
        row_depths = [d for _, d in tree_rows]
        dep_starts, dep_spans = compute_dependency_steps(nodes)
        edges = dependency_edges_detailed(nodes)
        by_id = {n["id"]: n for n in nodes}
        dep_inheritance = dependency_inheritance_display(nodes)
        outline_actions: dict[str, dict[str, bool]] = {}
        for n in nodes:
            nid = n["id"]
            outline_actions[nid] = {
                "can_indent": can_indent_outline(nodes, by_id, nid),
                "can_outdent": can_outdent_outline(by_id, nid),
            }
        gw = build_git_workflow_status(root)
        return {
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
            "outline_actions": outline_actions,
            "git_workflow": gw,
        }

    @api.get("/roadmap/fingerprint")
    def api_roadmap_fingerprint() -> dict[str, int]:
        root = get_repo_root()
        return {"fingerprint": roadmap_fingerprint(root)}

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
