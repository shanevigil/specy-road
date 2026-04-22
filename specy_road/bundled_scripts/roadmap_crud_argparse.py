"""Argparse setup for roadmap_crud."""

from __future__ import annotations

import argparse
from pathlib import Path

from roadmap_crud_dependency_ops import (
    cmd_add_dependency,
    cmd_list_dependencies,
    cmd_remove_dependency,
    cmd_set_dependencies,
)
from roadmap_edit_fields import ROADMAP_NODE_STATUSES

from roadmap_crud_ops import (
    cmd_add,
    cmd_archive,
    cmd_edit,
    cmd_list,
    cmd_set_gate_status,
    cmd_show,
)


def _p_list(sub: argparse._SubParsersAction) -> None:
    sp = sub.add_parser("list-nodes", help="List all nodes with chunk path")
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
            "Kebab-case codename. Optional: if omitted for a task, validate "
            "auto-derives one from --title (collisions get a short suffix)."
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
    sp.add_argument("--dependency", action="append", default=[])
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
        help="Append one dependency node_key if missing (uses edit_node_set_pairs / validate)",
    )
    sp.add_argument("node_id", metavar="NODE_ID")
    sp.add_argument("dep_node_key", metavar="DEP_NODE_KEY")
    sp.set_defaults(func=cmd_add_dependency)


def _p_remove_dependency(sub: argparse._SubParsersAction) -> None:
    sp = sub.add_parser(
        "remove-dependency",
        help="Remove one dependency node_key if present",
    )
    sp.add_argument("node_id", metavar="NODE_ID")
    sp.add_argument("dep_node_key", metavar="DEP_NODE_KEY")
    sp.set_defaults(func=cmd_remove_dependency)


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
    p.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repository root (default: git root or cwd).",
    )
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
    _p_archive(sub)
    return p
