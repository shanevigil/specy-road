"""Close ancestors whose last leaf descendant just completed.

``finish-this-task`` flips the leaf it finished and nothing else, so a phase or
milestone kept its authored ``status`` (usually ``Not Started``) forever after
its final leaf closed. ``roadmap.md``, ``brief``, and the PM GUI all showed the
parent as Complete because they read the computed rollup, while the chunk on
disk disagreed — and ``list-nodes`` reported the stale value. Flipping the
parent in the same bookkeeping commit keeps the authored graph honest instead of
relying on every reader to compute around it.

Nodes carrying a ``milestone_execution`` block are skipped on purpose: their
status is owned by the milestone-rollup state machine, which closes them only
once the rollup branch is proven merged (see
``bundled_scripts/reconcile_milestone_status.py``).
"""

from __future__ import annotations

import sys
from pathlib import Path


def rolled_up_stale_ancestor_ids(nodes: list[dict], node_id: str) -> list[str]:
    """Ancestors of ``node_id`` that rolled up to Complete but say otherwise.

    Nearest ancestor first, so a phase is only reached after the milestone
    beneath it has been closed.
    """
    by_id = {n["id"]: n for n in nodes if isinstance(n.get("id"), str)}
    out: list[str] = []
    current = by_id.get(node_id)
    seen: set[str] = set()
    while current is not None:
        parent_id = current.get("parent_id")
        if not isinstance(parent_id, str) or parent_id in seen:
            break
        seen.add(parent_id)
        parent = by_id.get(parent_id)
        if parent is None:
            break
        current = parent
        if parent.get("milestone_execution") is not None:
            continue
        if parent.get("rollup_status") != "Complete":
            continue
        if parent.get("status") == "Complete":
            continue
        out.append(parent_id)
    return out


def complete_rolled_up_ancestors(repo_root: Path, node_id: str) -> list[str]:
    """Set stale rolled-up ancestors of ``node_id`` to Complete.

    Returns the repo-relative chunk paths that changed so the caller can fold
    them into the bookkeeping commit it is already assembling. Each write is
    validated; an ancestor that cannot be flipped is reported with the manual
    command rather than aborting a finish that has already succeeded.
    """
    from roadmap_chunk_utils import find_chunk_path
    from roadmap_crud_ops import edit_node_set_pairs
    from roadmap_load import load_roadmap

    changed: list[str] = []
    root = repo_root.resolve()
    try:
        nodes = load_roadmap(root)["nodes"]
    except (KeyError, OSError, SystemExit, TypeError, ValueError):
        # load_roadmap reports a broken graph by exiting. This pass is status
        # hygiene layered on a finish that already succeeded, and the
        # validate/export step right after reports the real problem, so a graph
        # we cannot read is not ours to fail on.
        return changed
    # One pass is enough: a rollup is computed from leaf descendants only, so
    # closing a milestone never changes the phase above it.
    for ancestor in rolled_up_stale_ancestor_ids(nodes, node_id):
        touched = [find_chunk_path(root, ancestor)]
        try:
            edit_node_set_pairs(root, ancestor, [("status", "Complete")])
        except (OSError, ValueError) as e:
            print(
                f"[warn] {ancestor} rolled up to Complete but could not be "
                f"updated: {e}\n"
                f"  Run: specy-road edit-node {ancestor} --set status=Complete",
                file=sys.stderr,
            )
            continue
        print(f"[ok] {ancestor} status -> Complete (all leaf descendants complete)")
        touched.append(find_chunk_path(root, ancestor))
        for chunk in touched:
            if chunk is None:
                continue
            rel = str(chunk.relative_to(root))
            if rel not in changed:
                changed.append(rel)
    return changed
