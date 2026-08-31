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
from roadmap_chunk_utils import load_manifest_mapping


# Re-export the pure helpers so callers (and tests) only need this module.
__all__ = [
    "RoutingDecision",
    "chunk_max_lines",
    "default_chunk_for_parent",
    "insert_include_in_manifest",
    "pick_target_chunk",
    "simulate_chunk_lines",
    "validate_callback",
    "write_node_update",
    "write_with_routing",
]


def validate_callback(root: Path) -> Callable[[], None]:
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
    *,
    extra_files: dict[Path, str] | None = None,
) -> Path:
    """Route ``node`` to the right chunk, write atomically, validate, return chunk path.

    ``extra_files`` (abs path -> text) joins the same transaction, so a node's
    planning sheet is never left on disk after a rejected write.
    """
    decision = pick_target_chunk(root, parent_id, hint_chunk_arg, node)
    plan = AtomicWritePlan(root=root)
    plan.stage_chunk(decision.chunk_path, decision.nodes_after)
    for path, text in (extra_files or {}).items():
        plan.stage_text(path, text)
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
            f"(node {node.get('id')!r} {decision.new_chunk_reason})",
            file=sys.stderr,
        )
    plan.commit(validate_callback(root))
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


def _plan_overflow_relocation(
    plan: AtomicWritePlan,
    root: Path,
    node_id: str,
    chunk_path: Path,
    nodes_after: list[dict],
    max_lines: int,
) -> Path | None:
    """Stage a relocation when ``nodes_after`` would push ``chunk_path`` over the cap.

    Returns the chunk that will hold ``node_id``, or ``None`` when the edited
    chunk still fits and the caller should stage it as-is. Single-node chunks
    are exempt from the cap per validator policy, so they never relocate.
    """
    if len(nodes_after) < 2 or simulate_chunk_lines(nodes_after) <= max_lines:
        return None
    target = next(
        (n for n in nodes_after if isinstance(n, dict) and n.get("id") == node_id),
        None,
    )
    if target is None:
        return None
    pid_raw = target.get("parent_id")
    parent_id = pid_raw if isinstance(pid_raw, str) else None
    remaining = [
        n for n in nodes_after
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
    _stage_relocation(plan, root, parent_id, chunk_path, remaining, decision)
    _relocation_log(decision, node_id, chunk_path.name)
    return decision.chunk_path


def write_node_update(
    root: Path,
    node_id: str,
    chunk_path: Path,
    nodes_after: list[dict],
    *,
    renames: list[tuple[Path, Path]] | None = None,
    max_lines: int | None = None,
) -> Path:
    """Persist an edited chunk atomically; return the chunk holding ``node_id``.

    Everything an edit touches is staged before a single byte lands: the chunk
    itself, a relocation (plus manifest entry) when the edit pushed the chunk
    over the line cap, and any planning-sheet rename the edit implies. A
    validation failure therefore leaves the working tree exactly as it was,
    rather than a half-applied edit that blocks every later command.
    """
    if max_lines is None:
        max_lines = chunk_max_lines(root)
    plan = AtomicWritePlan(root=root)
    relocated = _plan_overflow_relocation(
        plan, root, node_id, chunk_path, nodes_after, max_lines
    )
    if relocated is None:
        plan.stage_chunk(chunk_path, nodes_after)
    for src, dst in renames or []:
        plan.stage_rename(src, dst)
    plan.commit(validate_callback(root))
    return relocated or chunk_path
