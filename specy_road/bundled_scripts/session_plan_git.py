"""Git-aware adjustments to a :class:`SessionPlan` so ``--plan`` matches pickup.

``compute_session_plan`` is intentionally pure (no git). Pickup, after sync,
drops leaves whose ``feature/rm-<codename>`` tip already marks them Complete
while the integration branch has not merged. This module applies the same filter
to ``ready`` and ``parallel_batches``, and surfaces claimed leaves that are in
the same state under ``finished_claimed``.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from specy_road.bundled_scripts.do_next_finished_unmerged import finished_unmerged_ids
from specy_road.bundled_scripts.roadmap_load import load_roadmap
from specy_road.bundled_scripts.session_plan import SessionPlan, compute_session_plan, _parallel_batches
from specy_road.git_workflow_config import resolve_integration_defaults
from specy_road.registry_yaml import read_registry, registry_path


def _nodes_by_id(nodes: list[dict]) -> dict[str, dict]:
    return {n["id"]: n for n in nodes if n.get("id")}


def enrich_session_plan_with_git(
    plan: SessionPlan,
    nodes: list[dict],
    *,
    repo_root: Path,
    remote: str,
    integration_branch: str,
) -> SessionPlan:
    """Return a plan whose pickup-facing fields reflect feature-branch tips."""
    by_id = _nodes_by_id(nodes)

    ready_nodes = [by_id[i] for i in plan.ready if i in by_id]
    finished_ready, _ = finished_unmerged_ids(
        ready_nodes,
        repo_root=repo_root,
        remote=remote,
        integration_branch=integration_branch,
    )

    active_nodes = [by_id[i] for i in plan.active if i in by_id]
    finished_active, _ = finished_unmerged_ids(
        active_nodes,
        repo_root=repo_root,
        remote=remote,
        integration_branch=integration_branch,
    )
    finished_claimed = sorted(finished_active & set(plan.active))

    new_ready = [i for i in plan.ready if i not in finished_ready]
    new_batches = _parallel_batches(plan.waves, new_ready)
    finished_unmerged = sorted(finished_ready)

    totals = dict(plan.totals)
    totals["ready"] = len(new_ready)
    if finished_unmerged:
        totals["finished_unmerged"] = len(finished_unmerged)
    if finished_claimed:
        totals["finished_claimed"] = len(finished_claimed)

    return replace(
        plan,
        ready=new_ready,
        parallel_batches=new_batches,
        finished_unmerged=finished_unmerged,
        finished_claimed=finished_claimed,
        totals=totals,
    )


def gather_session_plan(
    repo_root: Path, under: str | None
) -> tuple[list[dict], dict, SessionPlan]:
    """Load roadmap/registry and return a git-enriched session plan."""
    nodes = load_roadmap(repo_root)["nodes"]
    reg = read_registry(registry_path(repo_root))
    plan = compute_session_plan(nodes, reg, under=under)
    base, remote, _ = resolve_integration_defaults(
        repo_root, explicit_base=None, explicit_remote=None
    )
    plan = enrich_session_plan_with_git(
        plan,
        nodes,
        repo_root=repo_root,
        remote=remote,
        integration_branch=base,
    )
    return nodes, reg, plan
