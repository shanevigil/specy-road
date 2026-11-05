#!/usr/bin/env python3
"""Re-parent a node from the CLI, atomically.

The move/renumber logic has existed since the PM GUI's outline drag-and-drop
(``roadmap_outline_ops.move_node_outline``), but nothing exposed it to the CLI.
`edit-node --set parent_id=…` moves the *edge* and stops there: the node keeps
its old display id, so `M1.2` ends up hanging under `M2`. Re-parenting a leaf
therefore meant hand-editing two chunk files, renaming the planning sheet, and
re-pointing ``planning_dir``.

Two things had to be true before a CLI could be put over it, and only one was:

* **A move renumbers.** The subtree takes new ids — an id is a position in
  the outline, not an identity, which is why ``node_key`` exists — but a
  command that silently changed ids would be the same surprise the codename
  guard exists to prevent. So the ``old -> new`` map is printed. By default
  only the moved subtree is renumbered — for the CLI and the PM GUI's drag,
  indent and outdent alike: the moved node takes the next free id under its
  new parent (gaps are allowed), a chosen free id (``--id``) or the lowest
  gap (``--fill-gaps``), and its descendants follow it, so no sibling's or
  other milestone's id, sheet, claim or zone changes and every id cited
  elsewhere stays true. ``--renumber-outline`` (or a GUI request with
  ``renumber_outline: true``) instead renumbers the whole outline from its
  shape, closing the gaps the move leaves.
* **It was not atomic.** ``move_node_outline`` persists chunks, renames sheets
  and rewrites the registry, and only *then* validates; a rejected move left
  all three behind. That is the defect the ``v0.1.4`` round fixed for
  ``edit-node`` and never fixed here. This module stages the whole move through
  :class:`AtomicWritePlan` instead, so a move that fails to validate leaves the
  working tree byte-for-byte as it was.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from specy_road.bundled_scripts.roadmap_chunk_atomic import AtomicWritePlan
from specy_road.bundled_scripts.roadmap_crud_ops import (
    _refuse_if_milestone_locked,
    repo_root,
    run_validate_raise,
    unknown_node_msg,
)
from specy_road.bundled_scripts.roadmap_id_rewrite_staging import (
    _rewrite_touch_zones,
    _stage_merged_nodes,
    _stage_planning_moves,
    _stage_registry_ids,
)
from specy_road.bundled_scripts.roadmap_load import load_roadmap
from specy_road.bundled_scripts.roadmap_outline_ops import (
    _attach_at_index,
    _detach_reindex_old_parent,
    _validate_reparent_target,
    ordered_sibling_ids,
)
from specy_road.bundled_scripts.roadmap_outline_renumber import (
    assign_subtree_ids_inplace,
    check_chosen_child_id,
    lowest_free_child_id,
    next_free_child_id,
    renumber_display_ids_inplace,
    subtree_ids,
)
from specy_road.bundled_scripts.sync_planning_artifacts import (
    plan_planning_artifact_moves,
)
from specy_road.runtime_paths import add_repo_root_arg

ROOT_SENTINELS = ("", "null", "~", "none")


def stage_id_rewrite(
    root: Path,
    nodes: list[dict],
    scope: list[dict],
    old_to_new: dict[str, str],
    *,
    claims_in_map_only: bool,
) -> None:
    """Stage ``nodes`` plus the zone, sheet and claim rewrites an id map implies; commit.

    ``scope`` is every node a rewrite may touch. Shared by ``move_node`` and the
    PM GUI's ``reorder_siblings``; nothing reaches disk until the whole
    prospective graph validates.
    """
    renamed = {o: n for o, n in old_to_new.items() if o != n}
    _rewrite_touch_zones(scope, renamed)
    sheet_moves = plan_planning_artifact_moves(scope)

    plan = AtomicWritePlan(root)
    _stage_merged_nodes(plan, root, nodes)
    _stage_planning_moves(plan, root, sheet_moves)
    _stage_registry_ids(plan, root, renamed, claims_in_map_only=claims_in_map_only)
    plan.commit(lambda: run_validate_raise(root))


def _moved_node_id(
    nodes: list[dict],
    node_key: str,
    old_id: str,
    parent_id: str | None,
    new_id: str | None,
    fill_gaps: bool,
) -> str:
    """The id the moved node takes under a subtree-only move."""
    if new_id is None and not fill_gaps:
        return next_free_child_id(nodes, parent_id, exclude_key=node_key)
    ignore = subtree_ids(nodes, old_id)
    if fill_gaps:
        return lowest_free_child_id(nodes, parent_id, ignore_ids=ignore)
    check_chosen_child_id(nodes, parent_id, new_id, ignore_ids=ignore)
    return new_id


def move_node(
    root: Path,
    node_key: str,
    new_parent_id: str | None,
    new_index: int | None,
    *,
    renumber_outline: bool = False,
    new_id: str | None = None,
    fill_gaps: bool = False,
) -> dict[str, str]:
    """Re-parent ``node_key`` and renumber. Returns the ``old -> new`` id map.

    By default (the CLI and the PM GUI) only the moved subtree is renumbered,
    so the map and every sheet, claim and zone rewrite cover only it. The
    moved node takes ``new_id`` when given (a free direct child id of the new
    parent), the lowest free child id with ``fill_gaps``, else one past the
    highest. ``renumber_outline=True`` renumbers every display id from the tree
    shape and cannot be combined with either. Nothing reaches disk until the
    whole prospective graph validates.
    """
    if new_id is not None and fill_gaps:
        raise ValueError("--id and --fill-gaps (new_id, fill_gaps) are mutually exclusive")
    if renumber_outline and (new_id is not None or fill_gaps):
        raise ValueError(
            "--id/--fill-gaps renumber only the moved subtree and cannot be "
            "combined with --renumber-outline (renumber_outline)"
        )
    nodes = list(load_roadmap(root)["nodes"])
    by_key = {n["node_key"]: n for n in nodes if isinstance(n.get("node_key"), str)}
    if node_key not in by_key:
        raise ValueError(f"unknown node_key {node_key!r}")
    by_id = {n["id"]: n for n in nodes}
    moved = by_key[node_key]
    old_id = moved["id"]
    _validate_reparent_target(
        by_id, old_id, new_parent_id, moved_type=moved.get("type")
    )
    if new_index is None:
        siblings = [
            i
            for i in ordered_sibling_ids(nodes, new_parent_id, by_id)
            if i != old_id
        ]
        new_index = len(siblings)

    _detach_reindex_old_parent(nodes, by_id, moved.get("parent_id"), old_id)
    _attach_at_index(nodes, by_id, moved, old_id, new_parent_id, new_index)
    # ``scope`` is every node a rewrite may touch. A subtree move scopes it to
    # the subtree, so no node, sheet or claim outside it changes, even where
    # its text names a moved id.
    if renumber_outline:
        old_to_new = renumber_display_ids_inplace(nodes)
        scope = nodes
    else:
        target = _moved_node_id(
            nodes, node_key, old_id, new_parent_id, new_id, fill_gaps
        )
        old_to_new = assign_subtree_ids_inplace(nodes, node_key, target)
        new_ids = set(old_to_new.values())
        scope = [n for n in nodes if n["id"] in new_ids]
    stage_id_rewrite(
        root, nodes, scope, old_to_new, claims_in_map_only=not renumber_outline
    )
    return old_to_new


def _resolve_parent(raw: str, by_id: dict[str, dict], self_id: str) -> str | None:
    if raw.strip().lower() in ROOT_SENTINELS:
        return None
    pid = raw.strip()
    if pid == self_id:
        raise ValueError("--to-parent cannot be the node's own id")
    if pid not in by_id:
        raise ValueError(f"--to-parent {pid!r} is not an existing node id")
    return pid


def cmd_move(args: argparse.Namespace) -> None:
    root = repo_root(args)
    node_id = args.node_id
    by_id = {n["id"]: n for n in load_roadmap(root)["nodes"]}
    node = by_id.get(node_id)
    if node is None:
        print(f"error: {unknown_node_msg(node_id)}", file=sys.stderr)
        raise SystemExit(1)

    try:
        parent_id = _resolve_parent(args.to_parent, by_id, node_id)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        raise SystemExit(1) from None

    _refuse_if_milestone_locked(root, node_id)
    if parent_id is not None:
        _refuse_if_milestone_locked(root, parent_id)

    try:
        old_to_new = move_node(
            root,
            node["node_key"],
            parent_id,
            args.index,
            renumber_outline=args.renumber_outline,
            new_id=args.new_id,
            fill_gaps=args.fill_gaps,
        )
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        raise SystemExit(1) from None

    new_parent = old_to_new.get(parent_id, parent_id)
    where = f"under {new_parent}" if parent_id else "to the roadmap root"
    print(f"[ok] moved {old_to_new.get(node_id, node_id)} {where}")
    renamed = {o: n for o, n in old_to_new.items() if o != n}
    if not renamed:
        return
    print("\nDisplay ids changed (an id is a position, not an identity):")
    for old, new in sorted(renamed.items()):
        print(f"  {old} -> {new}")
    print(
        "\nPlanning sheets, touch-zone path segments equal to an old id, and "
        "roadmap/registry.yaml were updated to match (only for the renumbered "
        "nodes and their claims unless --renumber-outline was given). "
        "Any feature/rm-* branch keeps its codename; only ids moved."
    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="specy-road move-node",
        description=(
            "Re-parent a node and its subtree. The node takes the next free id "
            "under its new parent (or --id, or the lowest gap with --fill-gaps) "
            "and its descendants follow it; no other id changes "
            "(--renumber-outline renumbers the whole roadmap instead). "
            "In the same transaction it renames the renumbered nodes' planning "
            "sheets and, in those nodes and their registry claims, rewrites "
            "node_id and touch-zone path segments equal to an old id; nothing "
            "outside the moved subtree is rewritten. With --renumber-outline "
            "every node and claim is in scope."
        ),
    )
    p.add_argument("node_id", metavar="NODE_ID", help="The node to move (e.g. M1.2).")
    p.add_argument(
        "--to-parent",
        required=True,
        metavar="PARENT_NODE_ID",
        help=(
            "New parent's display id, or null/~ for the roadmap root. "
            "Unlike edit-node --set parent_id=, this renumbers."
        ),
    )
    p.add_argument(
        "--renumber-outline",
        action="store_true",
        help=(
            "Renumber every display id in the roadmap from the tree shape, "
            "closing the gaps the move leaves. Siblings "
            "and other milestones may change id, sheet name and claims."
        ),
    )
    p.add_argument(
        "--id",
        dest="new_id",
        default=None,
        metavar="NEW_ID",
        help=(
            "The moved node's new id: PARENT_NODE_ID plus one numeric segment "
            "(Mk at the root), not used by any node outside the moved subtree. "
            "Not with --fill-gaps or --renumber-outline."
        ),
    )
    p.add_argument(
        "--fill-gaps",
        action="store_true",
        help=(
            "Take the lowest unused child id under the new parent (from 1; at "
            "the root from 0 when M0 exists, else 1) instead of one past the "
            "highest. Not with --id or --renumber-outline."
        ),
    )
    p.add_argument(
        "--index",
        type=int,
        default=None,
        metavar="N",
        help=(
            "Position among the new siblings, 0-based (default: last). Sets the "
            "outline order only; without --renumber-outline the id is still the "
            "next free one (or --id / --fill-gaps)."
        ),
    )
    add_repo_root_arg(p)
    p.set_defaults(func=cmd_move)
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv if argv is not None else sys.argv[1:])
    args.func(args)


if __name__ == "__main__":
    main()
