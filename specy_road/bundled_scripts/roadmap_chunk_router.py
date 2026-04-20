"""Public entry points for automatic chunk routing.

Calls into :mod:`roadmap_chunk_router_pick` for the routing decision and
:mod:`roadmap_chunk_atomic` for the snapshot/commit/rollback cycle. Used by
``roadmap_crud_ops`` (CLI ``add-node`` / ``edit-node``) and
``gui_app_routes_nodes`` (PM Gantt ``/api/nodes/add``).

Atomic guarantee: chunk + manifest writes either all succeed and the merged
graph validates, or every affected file is restored to its pre-call bytes
(net-new files are unlinked).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable

from roadmap_chunk_atomic import AtomicWritePlan
from roadmap_chunk_router_pick import (
    RoutingDecision,
    chunk_max_lines,
    default_chunk_for_parent,
    insert_include_in_manifest,
    pick_target_chunk,
    simulate_chunk_lines,
)
from roadmap_chunk_utils import load_json_chunk, load_manifest_mapping


# Re-export the pure helpers so callers (and tests) only need this module.
__all__ = [
    "RoutingDecision",
    "chunk_max_lines",
    "default_chunk_for_parent",
    "insert_include_in_manifest",
    "pick_target_chunk",
    "relocate_node_if_overflow",
    "simulate_chunk_lines",
    "write_with_routing",
]


def _validate_callback(root: Path) -> Callable[[], None]:
    """Return a no-arg callable that re-raises ``ValueError`` from validation."""
    # Lazy import to avoid a circular import at module load time
    # (roadmap_crud_ops imports this module).
    from roadmap_crud_ops import run_validate_raise

    def _do() -> None:
        run_validate_raise(root)

    return _do


def write_with_routing(
    root: Path,
    parent_id: str | None,
    hint_chunk_arg: str | None,
    node: dict,
) -> Path:
    """Route ``node`` to the right chunk, write atomically, validate, return chunk path."""
    decision = pick_target_chunk(root, parent_id, hint_chunk_arg, node)
    plan = AtomicWritePlan(root=root)
    plan.stage_chunk(decision.chunk_path, decision.nodes_after)
    if decision.is_new_chunk:
        manifest_doc = load_manifest_mapping(root)
        base_for_insert = (
            hint_chunk_arg
            or default_chunk_for_parent(root, parent_id)
            or decision.chunk_rel
        )
        insert_include_in_manifest(manifest_doc, decision.chunk_rel, base_for_insert)
        plan.stage_manifest(manifest_doc)
        print(
            f"[chunk-router] auto-created chunk roadmap/{decision.chunk_rel} "
            f"(node {node.get('id')!r} would have overflowed existing chunks)",
            file=sys.stderr,
        )
    plan.commit(_validate_callback(root))
    return decision.chunk_path


def _stage_relocation(
    plan: AtomicWritePlan,
    root: Path,
    parent_id: str | None,
    chunk_path: Path,
    remaining: list[dict],
    decision: RoutingDecision,
) -> None:
    plan.stage_chunk(chunk_path, remaining)
    plan.stage_chunk(decision.chunk_path, decision.nodes_after)
    if decision.is_new_chunk:
        manifest_doc = load_manifest_mapping(root)
        base_for_insert = default_chunk_for_parent(root, parent_id) or decision.chunk_rel
        insert_include_in_manifest(manifest_doc, decision.chunk_rel, base_for_insert)
        plan.stage_manifest(manifest_doc)


def _relocation_log(
    decision: RoutingDecision, node_id: str, source_name: str
) -> None:
    if decision.is_new_chunk:
        print(
            f"[chunk-router] relocated node {node_id!r} into auto-created "
            f"chunk roadmap/{decision.chunk_rel} after edit pushed source over limit",
            file=sys.stderr,
        )
    else:
        print(
            f"[chunk-router] relocated node {node_id!r} from {source_name} "
            f"to roadmap/{decision.chunk_rel} after edit pushed source over limit",
            file=sys.stderr,
        )


def relocate_node_if_overflow(
    root: Path,
    node_id: str,
    chunk_path: Path,
    max_lines: int | None = None,
) -> Path | None:
    """If ``chunk_path`` exceeds the cap, move ``node_id`` to a fitting chunk.

    Returns the new chunk path on success, ``None`` if no relocation needed.
    Atomic + validated.
    """
    if max_lines is None:
        max_lines = chunk_max_lines(root)
    if not chunk_path.is_file():
        return None
    current_nodes = load_json_chunk(chunk_path)
    if simulate_chunk_lines(current_nodes) <= max_lines:
        return None
    target = next(
        (n for n in current_nodes if isinstance(n, dict) and n.get("id") == node_id),
        None,
    )
    if target is None:
        return None
    if len(current_nodes) == 1:
        # Single-node chunks are exempt from the cap (per validator policy).
        return None
    pid_raw = target.get("parent_id")
    parent_id = pid_raw if isinstance(pid_raw, str) else None
    remaining = [
        n for n in current_nodes
        if not (isinstance(n, dict) and n.get("id") == node_id)
    ]
    decision = pick_target_chunk(
        root,
        parent_id,
        hint_chunk_rel=None,
        new_node=target,
        max_lines=max_lines,
    )
    if decision.chunk_path == chunk_path and not decision.is_new_chunk:
        return None
    plan = AtomicWritePlan(root=root)
    _stage_relocation(plan, root, parent_id, chunk_path, remaining, decision)
    _relocation_log(decision, node_id, chunk_path.name)
    plan.commit(_validate_callback(root))
    return decision.chunk_path
