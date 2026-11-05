#!/usr/bin/env python3
"""`specy-road indent`, `outdent` and `group-nodes`: re-level siblings in one transaction.

Split from ``roadmap_move_node`` (file-limits cap). ``indent`` and ``outdent``
run the PM GUI's ``apply_indent`` / ``apply_outdent``; ``group-nodes`` creates a
parent and moves siblings under it. All three stage through ``move_nodes``, so
a batch is one ``AtomicWritePlan`` validated once.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from specy_road.bundled_scripts.planning_sheet_bootstrap import (
    plan_planning_sheet_for_new_node,
)
from specy_road.bundled_scripts.roadmap_chunk_atomic import AtomicWritePlan
from specy_road.bundled_scripts.roadmap_chunk_router_pick import (
    default_chunk_for_parent,
    insert_include_in_manifest,
    pick_target_chunk,
)
from specy_road.bundled_scripts.roadmap_chunk_utils import (
    PHASE_ROOT_REASON,
    load_manifest_mapping,
)
from specy_road.bundled_scripts.roadmap_crud_ops import (
    _refuse_if_milestone_locked,
    repo_root,
    unknown_node_msg,
)
from specy_road.bundled_scripts.roadmap_crud_prepare import (
    ensure_codename_for_new_node,
)
from specy_road.bundled_scripts.roadmap_gui_tree import indent_parent_id
from specy_road.bundled_scripts.roadmap_load import load_roadmap
from specy_road.bundled_scripts.roadmap_move_node import (
    NodeMove,
    move_nodes,
)
from specy_road.bundled_scripts.roadmap_node_keys import new_node_key
from specy_road.bundled_scripts.roadmap_outline_ops import (
    apply_indent,
    apply_outdent,
    ordered_sibling_ids,
    print_id_map,
)
from specy_road.bundled_scripts.roadmap_outline_renumber import check_chosen_child_id
from specy_road.milestone_lock import assert_pm_nodes_not_milestone_locked
from specy_road.runtime_paths import add_repo_root_arg


@dataclass(frozen=True)
class NewParent:
    """The node a group creates: ``index`` among its siblings, ``sheet`` as (path, text)."""

    root: Path
    node: dict
    index: int
    sheet: tuple[Path, str] | None

    def insert(self, nodes: list[dict]) -> None:
        """Add the node to ``nodes`` at its sibling position."""
        by_id = {n["id"]: n for n in nodes}
        siblings = ordered_sibling_ids(nodes, self.node["parent_id"], by_id)
        siblings.insert(self.index, self.node["id"])
        nodes.append(self.node)
        by_id[self.node["id"]] = self.node
        for i, nid in enumerate(siblings):
            by_id[nid]["sibling_order"] = i

    def stage(self, plan: AtomicWritePlan, nodes: list[dict]) -> None:
        """Stage the node into its routed chunk, over the batch's other chunk edits."""
        parent_id = self.node["parent_id"]
        decision = pick_target_chunk(self.root, parent_id, None, self.node)
        by_key = {n["node_key"]: n for n in nodes}
        plan.stage_chunk(
            decision.chunk_path, [by_key[n["node_key"]] for n in decision.nodes_after]
        )
        if decision.is_new_chunk:
            manifest = load_manifest_mapping(self.root)
            top_level = (
                decision.new_chunk_reason == PHASE_ROOT_REASON and parent_id is None
            )
            base = None if top_level else default_chunk_for_parent(self.root, parent_id)
            insert_include_in_manifest(manifest, decision.chunk_rel, base)
            plan.stage_manifest(manifest)
        if self.sheet is not None:
            plan.stage_text(*self.sheet)


def _common_parent(by_id: dict[str, dict], node_ids: Sequence[str]) -> str | None:
    """The parent ``node_ids`` share; ``ValueError`` unless they are distinct siblings."""
    if not node_ids:
        raise ValueError("group needs at least one node id")
    for nid in node_ids:
        if nid not in by_id:
            raise ValueError(unknown_node_msg(nid))
    if len(set(node_ids)) != len(node_ids):
        raise ValueError("a group's node ids must be distinct")
    parents = {by_id[nid].get("parent_id") or None for nid in node_ids}
    if len(parents) != 1:
        raise ValueError("a group's node ids must be siblings (one common parent)")
    return parents.pop()


def group_nodes(
    root: Path,
    into_new: str,
    title: str,
    node_ids: Sequence[str],
    *,
    node_type: str = "milestone",
) -> dict[str, str]:
    """Create ``into_new`` and move the sibling ``node_ids`` under it, in one transaction.

    The new parent takes the earliest listed sibling's position and a codename
    and sheet derived as ``add-node`` derives them; its children become
    ``into_new.1..N`` in argument order, each keeping its descendants' suffixes.
    Returns the ``old -> new`` id map; every refusal is a ``ValueError``.
    """
    nodes = list(load_roadmap(root)["nodes"])
    by_id = {n["id"]: n for n in nodes}
    parent_id = _common_parent(by_id, node_ids)
    check_chosen_child_id(nodes, parent_id, into_new, ignore_ids=set())
    node: dict = {
        "id": into_new,
        "node_key": new_node_key(),
        "parent_id": parent_id,
        "type": node_type,
        "title": title,
        "status": "Not Started",
        "dependencies": [],
        "touch_zones": [],
    }
    ensure_codename_for_new_node(root, node)
    sheet = plan_planning_sheet_for_new_node(root, node)
    siblings = ordered_sibling_ids(nodes, parent_id, by_id)
    index = min(siblings.index(nid) for nid in node_ids)
    moves = [
        NodeMove(by_id[nid]["node_key"], into_new, i, new_id=f"{into_new}.{i + 1}")
        for i, nid in enumerate(node_ids)
    ]
    return move_nodes(root, moves, new_parent=NewParent(root, node, index, sheet))


def _shift_target(root: Path, node_id: str) -> dict[str, dict]:
    """The graph by id, once ``node_id`` is known to exist and not be locked."""
    by_id = {n["id"]: n for n in load_roadmap(root)["nodes"]}
    if node_id not in by_id:
        print(f"error: {unknown_node_msg(node_id)}", file=sys.stderr)
        raise SystemExit(1)
    _refuse_if_milestone_locked(root, node_id)
    return by_id


def _run_shift(
    root: Path,
    node_id: str,
    shift: Callable[[Path, str], dict[str, str] | None],
    noop: str,
) -> None:
    """Run ``apply_indent`` / ``apply_outdent``; a no-op exits 1 printing ``noop``."""
    try:
        old_to_new = shift(root, node_id)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        raise SystemExit(1) from None
    if old_to_new is None:
        print(f"error: {noop}", file=sys.stderr)
        raise SystemExit(1)
    print(f"[ok] {node_id} is now {old_to_new[node_id]}")
    print_id_map(old_to_new)


def cmd_indent(args: argparse.Namespace) -> None:
    root = repo_root(args)
    node_id = args.node_id
    above = indent_parent_id(_shift_target(root, node_id), node_id)
    noop = "no previous sibling"
    if above is not None:
        # The sibling above becomes the parent: its subtree gains a node.
        _refuse_if_milestone_locked(root, above)
        noop = f"{node_id} cannot nest under {above} (node type or outline depth)"
    _run_shift(root, node_id, apply_indent, noop)


def cmd_outdent(args: argparse.Namespace) -> None:
    root = repo_root(args)
    _shift_target(root, args.node_id)
    _run_shift(root, args.node_id, apply_outdent, "already at root")


def cmd_group(args: argparse.Namespace) -> None:
    root = repo_root(args)
    try:
        # A locked parent locks its whole subtree, so the listed ids cover it.
        assert_pm_nodes_not_milestone_locked(
            load_roadmap(root)["nodes"], *args.node_ids
        )
        old_to_new = group_nodes(
            root, args.into_new, args.title, args.node_ids, node_type=args.type
        )
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        raise SystemExit(1) from None
    print(f"[ok] grouped {len(args.node_ids)} node(s) under new {args.into_new}")
    print_id_map(old_to_new)


def _add_shift_parser(sub, command: str, description: str, func) -> None:
    p = sub.add_parser(command, help=description, description=description)
    p.add_argument("node_id", metavar="NODE_ID", help="The node to shift (e.g. M1.2).")
    add_repo_root_arg(p)
    p.set_defaults(func=func)


def _add_group_parser(sub) -> None:
    description = (
        "Create a parent and move the listed siblings under it in one "
        "transaction, validated once. The parent takes the earliest listed "
        "sibling's position; its children become NEW_ID.1..N in argument "
        "order and their descendants keep their suffixes."
    )
    p = sub.add_parser("group-nodes", help=description, description=description)
    p.add_argument(
        "node_ids", nargs="+", metavar="NODE_ID", help="Distinct siblings to group."
    )
    p.add_argument(
        "--into-new",
        required=True,
        metavar="NEW_ID",
        help="The new parent's id: a free direct child id of the siblings' parent.",
    )
    p.add_argument("--title", required=True, help="The new parent's title.")
    p.add_argument(
        "--type",
        default="milestone",
        choices=["vision", "phase", "milestone", "task"],
        help="The new parent's type (default: milestone).",
    )
    add_repo_root_arg(p)
    p.set_defaults(func=cmd_group)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="specy-road")
    sub = p.add_subparsers(dest="command", required=True)
    _add_shift_parser(
        sub,
        "indent",
        "Nest a node and its subtree under the sibling above it, as the PM UI's "
        "indent does; only that subtree's ids change. With no sibling above, "
        "exits 1 and writes nothing.",
        cmd_indent,
    )
    _add_shift_parser(
        sub,
        "outdent",
        "Make a node the sibling after its parent, as the PM UI's outdent does; "
        "only its subtree's ids change. At the root, exits 1 and writes nothing.",
        cmd_outdent,
    )
    _add_group_parser(sub)
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv if argv is not None else sys.argv[1:])
    args.func(args)


if __name__ == "__main__":
    main()
