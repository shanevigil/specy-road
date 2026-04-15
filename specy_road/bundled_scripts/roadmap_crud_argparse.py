"""Argparse setup for roadmap_crud."""

from __future__ import annotations

import argparse
from pathlib import Path

from roadmap_crud_ops import cmd_add, cmd_archive, cmd_edit, cmd_list, cmd_show


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
        required=True,
        help="Chunk path under roadmap/ (e.g. phases/M1.json)",
    )
    sp.add_argument("--id", required=True, help="Node id, e.g. M1.2.1")
    sp.add_argument(
        "--type",
        required=True,
        choices=["vision", "phase", "milestone", "task"],
    )
    sp.add_argument("--title", required=True)
    sp.add_argument(
        "--parent-id",
        required=True,
        help="Parent id, or 'null' for phase roots",
    )
    sp.add_argument("--codename", default=None)
    sp.add_argument("--status", default="Not Started")
    sp.add_argument(
        "--execution-milestone",
        dest="execution_milestone",
        default=None,
    )
    sp.add_argument(
        "--execution-subtask",
        dest="execution_subtask",
        default=None,
        choices=["human", "agentic", "human-gate"],
    )
    sp.add_argument(
        "--parallel-tracks",
        dest="parallel_tracks",
        type=int,
        default=None,
    )
    sp.add_argument("--touch-zone", action="append", default=[])
    sp.add_argument("--dependency", action="append", default=[])
    _add_agentic_cli_flags(sp)
    sp.set_defaults(func=cmd_add)


def _add_agentic_cli_flags(sp: argparse.ArgumentParser) -> None:
    sp.add_argument("--checklist-json", default=None)
    sp.add_argument("--artifact-action", dest="artifact_action", default=None)
    sp.add_argument("--contract-citation", dest="contract_citation", default=None)
    sp.add_argument("--interface-contract", dest="interface_contract", default=None)
    sp.add_argument("--constraints-note", dest="constraints_note", default=None)
    sp.add_argument("--dependency-note", dest="dependency_note", default=None)


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
    _p_archive(sub)
    return p
