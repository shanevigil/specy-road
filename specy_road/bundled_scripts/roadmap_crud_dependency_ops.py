"""Roadmap dependency CRUD for the CLI (same edit path as the PM GUI patch)."""

from __future__ import annotations

import sys
from pathlib import Path

from specy_road.bundled_scripts.roadmap_chunk_utils import find_chunk_path
from specy_road.bundled_scripts.roadmap_crud_ops import edit_node_set_pairs, repo_root, unknown_node_msg
from specy_road.bundled_scripts.roadmap_load import load_roadmap


def merged_node_by_id(root: Path, node_id: str) -> dict | None:
    for n in load_roadmap(root)["nodes"]:
        if isinstance(n, dict) and n.get("id") == node_id:
            return n
    return None


def _dependencies_patch_value(keys: list[str]) -> str:
    """String for ``dependencies=`` patches (same ordering as the PM GUI)."""
    return " ".join(sorted(keys))


def _archived_keys(root) -> set[str]:
    """Archived node_keys, or empty when the ledger is absent/unreadable."""
    try:
        from specy_road.archive_index import archived_node_keys

        return archived_node_keys(root)
    except Exception:  # noqa: BLE001 - listing must not depend on the ledger
        return set()


def cmd_list_dependencies(args: object) -> None:
    root = repo_root(args)
    nid = args.node_id
    rec = merged_node_by_id(root, nid)
    if not rec:
        print(f"error: {unknown_node_msg(nid)}", file=sys.stderr)
        raise SystemExit(1)
    deps = [str(x) for x in (rec.get("dependencies") or []) if x]
    if not deps:
        print("(none)")
        return
    nodes = load_roadmap(root)["nodes"]
    by_key: dict[str, dict] = {}
    for n in nodes:
        if isinstance(n, dict):
            k = n.get("node_key")
            if isinstance(k, str) and k:
                by_key[k] = n
    for dk in deps:
        row = by_key.get(dk)
        if row:
            oid = str(row.get("id", ""))
            title = str(row.get("title", ""))[:72]
            print(f"{dk}\t{oid}\t{title}")
        else:
            label = (
                "(archived — restore-archive to bring it back)"
                if dk in _archived_keys(root)
                else "(missing node_key in roadmap)"
            )
            print(f"{dk}\t?\t{label}")


def cmd_set_dependencies(args: object) -> None:
    root = repo_root(args)
    nid = args.node_id
    raw = "" if args.clear else (args.deps_raw or "")
    try:
        edit_node_set_pairs(root, nid, [("dependencies", raw)])
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        raise SystemExit(1) from None
    chunk = find_chunk_path(root, nid)
    assert chunk is not None
    print(f"[ok] dependencies updated for {nid} in {chunk.relative_to(root)}")


def cmd_add_dependency(args: object) -> None:
    root = repo_root(args)
    nid = args.node_id
    dep_key = args.dep_node_key
    rec = merged_node_by_id(root, nid)
    if not rec:
        print(f"error: {unknown_node_msg(nid)}", file=sys.stderr)
        raise SystemExit(1)
    cur = [str(x) for x in (rec.get("dependencies") or []) if x]
    if dep_key in cur:
        print(f"[ok] {nid} already lists dependency {dep_key!r}")
        return
    cur.append(dep_key)
    try:
        edit_node_set_pairs(
            root, nid, [("dependencies", _dependencies_patch_value(cur))]
        )
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        raise SystemExit(1) from None
    chunk = find_chunk_path(root, nid)
    assert chunk is not None
    print(f"[ok] added {dep_key!r} to {nid} in {chunk.relative_to(root)}")


def cmd_remove_dependency(args: object) -> None:
    root = repo_root(args)
    nid = args.node_id
    dep_key = args.dep_node_key
    rec = merged_node_by_id(root, nid)
    if not rec:
        print(f"error: {unknown_node_msg(nid)}", file=sys.stderr)
        raise SystemExit(1)
    cur = [str(x) for x in (rec.get("dependencies") or []) if x]
    if dep_key not in cur:
        print(f"[ok] {nid} did not list dependency {dep_key!r}")
        return
    new_keys = [x for x in cur if x != dep_key]
    try:
        edit_node_set_pairs(
            root, nid, [("dependencies", _dependencies_patch_value(new_keys))]
        )
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        raise SystemExit(1) from None
    chunk = find_chunk_path(root, nid)
    assert chunk is not None
    print(f"[ok] removed {dep_key!r} from {nid} in {chunk.relative_to(root)}")
