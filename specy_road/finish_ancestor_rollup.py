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

With ``policy.milestone_full_review`` on (the default, read like the rest of
the review policy) a milestone — a node with leaf children — is **held** when
its last leaf finishes: it keeps its authored status, and the public loader's
computed ``rollup_status`` stays non-Complete, until a full review of its
combined change passes the review gate at the integration tip. Ancestors
above it wait with it. ``specy-road mark-implementation-reviewed
<MILESTONE_ID>`` then closes it through :func:`complete_reviewed_milestone`.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

from specy_road.milestone_review_hold import (
    UNRESOLVABLE_HOLD,
    held_milestones,
    milestone_review_hold,
    milestone_review_hold_notice,
    milestone_review_next_steps,
)


def rolled_up_stale_ancestor_ids(
    nodes: list[dict], node_id: str, held: Callable[[str], str | None] | None = None
) -> list[str]:
    """Ancestors of ``node_id`` that rolled up to Complete but say otherwise.

    Nearest ancestor first, so a phase is only reached after the milestone
    beneath it has been closed. ``held(ancestor_id)`` returns why that ancestor
    must keep its status (its full review is pending), which ends the walk:
    nothing above a held milestone closes before it does.
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
        if held is not None and held(parent_id):
            break
        out.append(parent_id)
    return out


def _print_hold(repo_root: Path, nodes: list[dict]) -> Callable[[str], str | None]:
    """A ``held`` callback that reports each hold once and opens the hand-off directory for it."""
    from specy_road.review_files import reviews_dir

    def held(ancestor: str) -> str | None:
        why = milestone_review_hold(repo_root, nodes, ancestor)
        if why:
            reviews_dir(repo_root, ancestor).mkdir(parents=True, exist_ok=True)   # handoff status lists it
            print(f"[hold] {ancestor} rolled up to Complete but {why}; its status is unchanged.")
            print(milestone_review_next_steps(ancestor))
        return why

    return held


def _set_complete(root: Path, node_id: str) -> list[str]:
    """Set ``node_id`` to Complete; the repo-relative chunk paths that changed (empty on failure).

    Writes the chunk like ``finish-this-task`` patches the finished leaf: no
    nested ``edit-node`` validate, so finish's later validate prints each
    warning once.
    """
    from specy_road.roadmap_chunk_utils import (
        find_chunk_path,
        load_json_chunk,
        write_json_chunk,
    )

    chunk = find_chunk_path(root, node_id)
    if not chunk or chunk.suffix.lower() != ".json":
        print(
            f"[warn] {node_id} rolled up to Complete but could not be "
            f"updated: chunk file is missing or not .json\n"
            f"  Run: specy-road edit-node {node_id} --set status=Complete",
            file=sys.stderr,
        )
        return []
    try:
        nodes = load_json_chunk(chunk)
        for n in nodes:
            if n.get("id") == node_id:
                n["status"] = "Complete"
                write_json_chunk(chunk, nodes)
                print(f"[ok] {node_id} status -> Complete (all leaf descendants complete)")
                return [str(chunk.relative_to(root))]
    except (OSError, ValueError) as e:
        print(
            f"[warn] {node_id} rolled up to Complete but could not be "
            f"updated: {e}\n"
            f"  Run: specy-road edit-node {node_id} --set status=Complete",
            file=sys.stderr,
        )
        return []
    print(
        f"[warn] {node_id} rolled up to Complete but could not be "
        f"updated: node not found in {chunk.relative_to(root)}\n"
        f"  Run: specy-road edit-node {node_id} --set status=Complete",
        file=sys.stderr,
    )
    return []


def _leaf_annotated(root: Path) -> list[dict]:
    """``load_roadmap`` then restore leaf-based rollup for the authored-status walk."""
    from specy_road.roadmap_graph import compute_rollup_status
    from specy_road.roadmap_load import load_roadmap

    nodes = load_roadmap(root)["nodes"]
    leaf = compute_rollup_status(nodes)
    for n in nodes:
        nid = n.get("id")
        if isinstance(nid, str) and nid in leaf:
            n["rollup_status"] = leaf[nid]
    return nodes


def complete_rolled_up_ancestors(repo_root: Path, node_id: str) -> list[str]:
    """Set stale rolled-up ancestors of ``node_id`` to Complete.

    Returns the repo-relative chunk paths that changed so the caller can fold
    them into the bookkeeping commit it is already assembling. Status is
    patched in the chunk without a nested validate (finish's later
    validate/export/digest run is the one pass); an ancestor that cannot be
    flipped is reported with the manual command rather than aborting a finish
    that has already succeeded.
    """
    changed: list[str] = []
    root = repo_root.resolve()
    try:
        nodes = _leaf_annotated(root)
    except (KeyError, OSError, SystemExit, TypeError, ValueError):
        # load_roadmap reports a broken graph by exiting. This pass is status
        # hygiene layered on a finish that already succeeded, and the
        # validate/export step right after reports the real problem, so a graph
        # we cannot read is not ours to fail on.
        return changed
    # One pass is enough: a rollup is computed from leaf descendants only, so
    # closing a milestone never changes the phase above it.
    for ancestor in rolled_up_stale_ancestor_ids(nodes, node_id, held=_print_hold(root, nodes)):
        for rel in _set_complete(root, ancestor):
            if rel not in changed:
                changed.append(rel)
    return changed


def complete_reviewed_milestone(repo_root: Path, node_id: str) -> list[str]:
    """Close a milestone whose full review passed, then the stale ancestors above it.

    The caller has checked the gate. Raises ``ValueError`` while a leaf under
    it is still open: the review covered a change that is not finished.
    Returns the repo-relative chunk paths that changed.
    """
    from specy_road.roadmap_graph import compute_rollup_status

    root = repo_root.resolve()
    nodes = _leaf_annotated(root)
    node = next((n for n in nodes if n.get("id") == node_id), None)
    if node is None:
        raise ValueError(f"unknown node id: {node_id}")
    if compute_rollup_status(nodes).get(node_id) != "Complete":
        raise ValueError(f"{node_id} still has unfinished leaves ({node.get('rollup_status')}); "
                         "its full review closes it only after the last one lands")
    changed = _set_complete(root, node_id) if node.get("status") != "Complete" else []
    for rel in complete_rolled_up_ancestors(root, node_id):
        if rel not in changed:
            changed.append(rel)
    return changed
