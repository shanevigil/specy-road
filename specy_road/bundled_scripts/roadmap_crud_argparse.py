"""Argparse setup for roadmap_crud."""

from __future__ import annotations

import argparse

from specy_road.bundled_scripts.roadmap_crud_dependency_ops import (
    cmd_add_dependency,
    cmd_apply,
    cmd_list_dependencies,
    cmd_remove_dependency,
    cmd_set_dependencies,
)
from specy_road.bundled_scripts.roadmap_edit_fields import ROADMAP_NODE_STATUSES

from specy_road.bundled_scripts.roadmap_crud_ops import (
    cmd_add,
    cmd_archive,
    cmd_edit,
    cmd_list,
    cmd_set_gate_status,
    cmd_show,
)
from specy_road.runtime_paths import add_repo_root_arg


def _p_list(sub: argparse._SubParsersAction) -> None:
    sp = sub.add_parser("list-nodes", help="List all nodes with chunk path")
    sp.add_argument(
        "--status",
        action="append",
        choices=sorted(ROADMAP_NODE_STATUSES),
        metavar="STATUS",
        help=(
            "Keep only nodes with this ROLLUP status — what roadmap.md and the "
            "PM GUI show, which for a parent is rolled up from its leaves rather "
            "than read off its own field. Repeatable. One of: "
            + ", ".join(sorted(ROADMAP_NODE_STATUSES))
        ),
    )
    sp.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="Print a JSON array of full node objects (titles untruncated), each with its chunk path",
    )
    sp.set_defaults(func=cmd_list)


def _p_show(sub: argparse._SubParsersAction) -> None:
    sp = sub.add_parser("show-node", help="Print one node as JSON")
    sp.add_argument("node_id", metavar="NODE_ID")
    sp.set_defaults(func=cmd_show)


def _p_add(sub: argparse._SubParsersAction) -> None:
    sp = sub.add_parser("add-node", help="Append a node to a chunk file")
    sp.add_argument(
        "--chunk",
        required=False,
        default=None,
        help=(
            "Optional chunk hint under roadmap/ (e.g. phases/M1.json). "
            "If omitted or full, specy-road auto-routes to a valid chunk in "
            "the same phase (creating one if needed)."
        ),
    )
    sp.add_argument("--id", required=True, help="Node id, e.g. M1.2.1")
    sp.add_argument(
        "--type",
        required=True,
        choices=["vision", "phase", "milestone", "task", "gate"],
    )
    sp.add_argument("--title", required=True)
    sp.add_argument(
        "--parent-id",
        required=True,
        help="Parent id, or 'null' for phase roots",
    )
    sp.add_argument(
        "--codename",
        default=None,
        help=(
            "Kebab-case codename. Optional: if omitted, it is derived from "
            "--title for every new node (collisions get a short suffix)."
        ),
    )
    sp.add_argument("--status", default="Not Started")
    sp.add_argument(
        "--execution-milestone",
        dest="execution_milestone",
        default=None,
    )
    sp.add_argument(
        "--parallel-tracks",
        dest="parallel_tracks",
        type=int,
        default=None,
    )
    sp.add_argument("--touch-zone", action="append", default=[])
    sp.add_argument(
        "--dependency",
        action="append",
        default=[],
        help="Node this one depends on: display id (M1.2) or node_key; stored as the node_key. Repeatable.",
    )
    sp.add_argument(
        "--acceptance",
        action="append",
        default=[],
        help="One acceptance criterion; repeat for each ('|' is not a separator).",
    )
    sp.add_argument("--sensitivity", default=None, help="Data-sensitivity class (default public); see roadmap/orchestration.yaml may_process")
    sp.add_argument("--executor-eligibility", dest="executor_eligibility", default=None, help="any (default) or a roster class tag such as senior")
    sp.add_argument(
        "--sibling-order",
        dest="sibling_order",
        type=int,
        default=None,
        help="Position among siblings (default: after the current last sibling).",
    )
    sp.set_defaults(func=cmd_add)


def _p_edit(sub: argparse._SubParsersAction) -> None:
    sp = sub.add_parser("edit-node", help="Patch fields on a node (--set key=value)")
    sp.add_argument("node_id", metavar="NODE_ID")
    sp.add_argument(
        "--set",
        dest="set",
        action="append",
        required=True,
        metavar="KEY=VALUE",
        help=(
            "Field to set; repeatable. List fields (acceptance, risks, touch_zones, "
            "dependencies) take one --set per item: --set acceptance='Saves offline' "
            "--set acceptance='Syncs on reconnect'. touch_zones also splits on commas; "
            "'|' is not a separator. An empty value (acceptance=) removes the field."
        ),
    )
    sp.add_argument(
        "--sync-codename",
        action="store_true",
        help=(
            "Re-derive the codename from a new --set title even when the "
            "current one was chosen by hand. Editing a title re-derives a "
            "title-derived codename automatically; a hand-picked one is kept, "
            "because the codename is the branch identity "
            "(feature/rm-<codename>) and the registry key. Renaming it "
            "mid-flight desynchronizes a live branch from its node."
        ),
    )
    sp.set_defaults(func=cmd_edit)


def _p_set_gate_status(sub: argparse._SubParsersAction) -> None:
    sp = sub.add_parser(
        "set-gate-status",
        help="Set roadmap status on a type gate node only",
    )
    sp.add_argument("node_id", metavar="NODE_ID")
    sp.add_argument(
        "--status",
        required=True,
        choices=sorted(ROADMAP_NODE_STATUSES),
        help="Roadmap status (same enum as other node types).",
    )
    sp.set_defaults(func=cmd_set_gate_status)


def _p_list_dependencies(sub: argparse._SubParsersAction) -> None:
    sp = sub.add_parser(
        "list-dependencies",
        help="Print explicit dependency node_keys for a node (tab: node_key, id, title)",
    )
    sp.add_argument("node_id", metavar="NODE_ID")
    sp.set_defaults(func=cmd_list_dependencies)


def _p_set_dependencies(sub: argparse._SubParsersAction) -> None:
    sp = sub.add_parser(
        "set-dependencies",
        help="Replace explicit dependencies (node_keys); same validation as PM GUI patch",
    )
    sp.add_argument("node_id", metavar="NODE_ID")
    mx = sp.add_mutually_exclusive_group(required=True)
    mx.add_argument(
        "--clear",
        action="store_true",
        help="Remove all explicit dependencies on this node",
    )
    mx.add_argument(
        "--deps",
        dest="deps_raw",
        metavar="KEYS",
        help="Space/comma/semicolon-separated dependency node_keys (same as edit-node dependencies=…)",
    )
    sp.set_defaults(func=cmd_set_dependencies)


def _p_add_dependency(sub: argparse._SubParsersAction) -> None:
    sp = sub.add_parser(
        "add-dependency",
        help="Append one dependency if missing (uses edit_node_set_pairs / validate)",
    )
    sp.add_argument("node_id", metavar="NODE_ID")
    sp.add_argument(
        "dep_node_key",
        metavar="DEP",
        help="Display id (M1.2) or node_key; stored as the node_key",
    )
    sp.set_defaults(func=cmd_add_dependency)


def _p_remove_dependency(sub: argparse._SubParsersAction) -> None:
    sp = sub.add_parser(
        "remove-dependency",
        help="Remove one dependency node_key if present",
    )
    sp.add_argument("node_id", metavar="NODE_ID")
    sp.add_argument("dep_node_key", metavar="DEP_NODE_KEY")
    sp.set_defaults(func=cmd_remove_dependency)


def _p_apply(sub: argparse._SubParsersAction) -> None:
    sp = sub.add_parser(
        "apply",
        help="Run a YAML file of add-node / edit-node / add-dependency changes as one batch",
        description=(
            "Apply a change file in order, all or nothing: if any change is "
            "refused, every file the batch touched is restored. Each entry is "
            "op: plus the subcommand's long options (node: and dependency: for "
            "the positionals, set: {field: value} for edit-node). See "
            "docs/roadmap-authoring.md."
        ),
    )
    sp.add_argument("changes_file", metavar="CHANGES.yaml")
    sp.add_argument(
        "--dry-run",
        action="store_true",
        help="Rehearse on a scratch copy and print the resulting waves; write nothing",
    )
    sp.set_defaults(func=cmd_apply)


def _p_archive(sub: argparse._SubParsersAction) -> None:
    sp = sub.add_parser(
        "archive-node",
        help="Remove the node from the roadmap JSON (--hard-remove). Soft Cancelled is removed from the schema.",
    )
    sp.add_argument("node_id", metavar="NODE_ID")
    sp.add_argument(
        "--hard-remove",
        action="store_true",
        help="Remove node from chunk (fails if parent/dependency refs exist)",
    )
    sp.set_defaults(func=cmd_archive)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="PM-oriented roadmap CRUD: list/show/add/edit/archive nodes.",
    )
    add_repo_root_arg(p)
    sub = p.add_subparsers(dest="cmd", required=True)
    _p_list(sub)
    _p_show(sub)
    _p_add(sub)
    _p_edit(sub)
    _p_set_gate_status(sub)
    _p_list_dependencies(sub)
    _p_set_dependencies(sub)
    _p_add_dependency(sub)
    _p_remove_dependency(sub)
    _p_apply(sub)
    _p_archive(sub)
    return p
