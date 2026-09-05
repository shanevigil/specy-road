#!/usr/bin/env python3
"""Re-parent a node from the CLI, atomically.

The move/renumber logic has existed since the PM GUI's outline drag-and-drop
(``roadmap_outline_ops.move_node_outline``), but nothing exposed it to the CLI.
`edit-node --set parent_id=…` moves the *edge* and stops there: the node keeps
its old display id, so `M1.2` ends up hanging under `M2`. Re-parenting a leaf
therefore meant hand-editing two chunk files, renaming the planning sheet, and
re-pointing ``planning_dir``.

Two things had to be true before a CLI could be put over it, and only one was:

* **A move renumbers.** The subtree takes new ids, and so do both sibling
  ranges it leaves and joins. That is correct — an id is a position in the
  outline, not an identity, which is why ``node_key`` exists — but a command
  that silently changed ids would be the same surprise the codename guard
  exists to prevent. So the ``old -> new`` map is printed.
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

import yaml

from specy_road.bundled_scripts.roadmap_chunk_atomic import AtomicWritePlan
from specy_road.bundled_scripts.roadmap_chunk_utils import (
    load_json_chunk,
    manifest_includes,
    roadmap_dir,
)
from specy_road.bundled_scripts.roadmap_crud_ops import (
    _refuse_if_milestone_locked,
    repo_root,
    run_validate_raise,
    unknown_node_msg,
)
from specy_road.bundled_scripts.roadmap_load import load_roadmap
from specy_road.bundled_scripts.roadmap_outline_ops import (
    _attach_at_index,
    _detach_reindex_old_parent,
    _validate_reparent_target,
    ordered_sibling_ids,
)
from specy_road.bundled_scripts.roadmap_outline_renumber import (
    renumber_display_ids_inplace,
)
from specy_road.bundled_scripts.planning_artifacts import resolve_planning_path
from specy_road.bundled_scripts.sync_planning_artifacts import (
    plan_planning_artifact_moves,
)
from specy_road.registry_yaml import registry_path
from specy_road.runtime_paths import add_repo_root_arg

ROOT_SENTINELS = ("", "null", "~", "none")


def _stage_merged_nodes(plan: AtomicWritePlan, root: Path, merged: list[dict]) -> None:
    """Stage every chunk rewritten by the move, matching ``persist_merged_nodes``."""
    by_key = {n["node_key"]: n for n in merged}
    base = roadmap_dir(root)
    for rel in manifest_includes(root):
        path = (base / rel).resolve()
        if not path.is_file() or path.suffix.lower() != ".json":
            continue
        out = []
        for old in load_json_chunk(path):
            key = old.get("node_key")
            if not isinstance(key, str) or key not in by_key:
                raise ValueError(f"chunk {rel}: unknown node_key {key!r}")
            out.append(by_key[key])
        plan.stage_chunk(path, out)


def _stage_planning_moves(
    plan: AtomicWritePlan, root: Path, moves: list[tuple[str, str, str]]
) -> None:
    """Stage the sheet renames a renumber implies.

    Every source is read before anything is staged for deletion, because a
    renumber routinely produces chains (``M1.3`` -> ``M1.2`` -> ``M1.1``) and a
    naive rename-at-a-time would consume a file another move still needs.
    """
    payloads: dict[Path, str] = {}
    sources: list[Path] = []
    for _nk, old_rel, new_rel in moves:
        src = resolve_planning_path(root, old_rel)
        if not src.is_file():
            continue
        payloads[resolve_planning_path(root, new_rel)] = src.read_text(
            encoding="utf-8"
        )
        sources.append(src)
    for dst, text in payloads.items():
        plan.stage_text(dst, text)
    for src in sources:
        if src not in payloads:
            plan.stage_delete(src)


def _stage_registry_ids(
    plan: AtomicWritePlan, root: Path, old_to_new: dict[str, str]
) -> None:
    """Stage the registry rewrite so claims still point at the moved nodes."""
    path = registry_path(root)
    if not old_to_new or not path.is_file():
        return
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("entries"), list):
        return
    changed = False
    for entry in data["entries"]:
        if not isinstance(entry, dict):
            continue
        nid = entry.get("node_id")
        if isinstance(nid, str) and nid in old_to_new:
            entry["node_id"] = old_to_new[nid]
            changed = True
    if changed:
        plan.stage_text(
            path,
            yaml.dump(
                data, default_flow_style=False, allow_unicode=True, sort_keys=False
            ),
        )


def move_node(
    root: Path, node_key: str, new_parent_id: str | None, new_index: int | None
) -> dict[str, str]:
    """Re-parent ``node_key`` and renumber. Returns the ``old -> new`` id map.

    Nothing reaches disk until the whole prospective graph validates.
    """
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
    old_to_new = renumber_display_ids_inplace(nodes)
    sheet_moves = plan_planning_artifact_moves(nodes)

    plan = AtomicWritePlan(root)
    _stage_merged_nodes(plan, root, nodes)
    _stage_planning_moves(plan, root, sheet_moves)
    _stage_registry_ids(plan, root, old_to_new)
    plan.commit(lambda: run_validate_raise(root))
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
        old_to_new = move_node(root, node["node_key"], parent_id, args.index)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        raise SystemExit(1) from None

    where = f"under {parent_id}" if parent_id else "to the roadmap root"
    print(f"[ok] moved {old_to_new.get(node_id, node_id)} {where}")
    renamed = {o: n for o, n in old_to_new.items() if o != n}
    if not renamed:
        return
    print("\nDisplay ids changed (an id is a position, not an identity):")
    for old, new in sorted(renamed.items()):
        print(f"  {old} -> {new}")
    print(
        "\nPlanning sheets and roadmap/registry.yaml were updated to match. "
        "Any feature/rm-* branch keeps its codename; only ids moved."
    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="specy-road move-node",
        description=(
            "Re-parent a node and its subtree, renumbering display ids across "
            "the roadmap. Renames planning sheets and updates registry claims "
            "in the same transaction."
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
        "--index",
        type=int,
        default=None,
        metavar="N",
        help="Position among the new siblings, 0-based (default: last).",
    )
    add_repo_root_arg(p)
    p.set_defaults(func=cmd_move)
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv if argv is not None else sys.argv[1:])
    args.func(args)


if __name__ == "__main__":
    main()
