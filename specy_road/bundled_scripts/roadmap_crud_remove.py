"""The destructive removal path: ``archive-node --hard-remove``.

Split out of :mod:`roadmap_crud_ops` to keep that module under the file-line
constraint, and because this is genuinely a different operation from the rest of
CRUD: it deletes a node and its planning sheet outright, with no way back.

Not to be confused with ``specy-road archive`` (:mod:`specy_road.archive_ops`),
which moves completed work out of the live graph **reversibly**. The name
collision is historical.
"""

from __future__ import annotations

import sys
from pathlib import Path

from planning_sheet_bootstrap import remove_planning_sheet_if_present
from roadmap_chunk_utils import find_chunk_path, load_json_chunk, write_json_chunk
from roadmap_load import load_roadmap

from roadmap_crud_ops import (
    node_index_in_chunk,
    repo_root,
    run_validate_raise,
    unknown_node_msg,
)


def can_hard_remove(root: Path, node_id: str) -> tuple[bool, str]:
    """Refuse when anything still points at the node — children or dependencies."""
    nodes = load_roadmap(root)["nodes"]
    target_key: str | None = None
    for n in nodes:
        if n.get("id") == node_id:
            target_key = n.get("node_key")
            break
    for n in nodes:
        if n.get("parent_id") == node_id:
            return False, f"child node {n['id']} has parent_id {node_id!r}"
        if target_key and target_key in (n.get("dependencies") or []):
            return False, f"node {n['id']} depends on node_key of {node_id!r}"
    return True, ""


def delete_roadmap_node_hard(root: Path, node_id: str) -> None:
    """Remove a node from its JSON chunk. Raises ``ValueError`` if not removable."""
    chunk = find_chunk_path(root, node_id)
    if not chunk:
        raise ValueError(unknown_node_msg(node_id))
    if chunk.suffix.lower() != ".json":
        raise ValueError(f"unsupported chunk type {chunk.suffix}")
    nodes = load_json_chunk(chunk)
    idx = node_index_in_chunk(nodes, node_id)
    if idx is None:
        raise ValueError(f"node {node_id!r} not found")
    ok, msg = can_hard_remove(root, node_id)
    if not ok:
        raise ValueError(msg)
    removed = nodes[idx]
    remove_planning_sheet_if_present(root, removed.get("planning_dir"))
    del nodes[idx]
    write_json_chunk(chunk, nodes)
    run_validate_raise(root)


def cmd_archive(args: object) -> None:
    root = repo_root(args)
    nid = args.node_id
    if args.hard_remove:
        try:
            delete_roadmap_node_hard(root, nid)
        except ValueError as e:
            print(f"error: {e}", file=sys.stderr)
            raise SystemExit(1) from None
        print(f"[ok] removed {nid}")
        return
    print(
        "error: archive-node without --hard-remove is no longer supported "
        "(Cancelled was removed from the roadmap schema).\n"
        "  To retire completed work reversibly, use the archive feature instead:\n"
        "    specy-road archive <NODE_ID>       (restore with: restore-archive)\n"
        "  To delete a node outright, pass --hard-remove after team agreement, "
        "or edit the JSON chunk.",
        file=sys.stderr,
    )
    raise SystemExit(1)
