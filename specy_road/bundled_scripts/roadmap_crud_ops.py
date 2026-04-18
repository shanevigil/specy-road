"""Roadmap CRUD command implementations (used by roadmap_crud.py)."""

from __future__ import annotations

import contextlib
import io
import json
import sys
from pathlib import Path

from roadmap_chunk_utils import (
    build_node_chunk_map,
    find_chunk_path,
    load_json_chunk,
    resolve_chunk_file,
    write_json_chunk,
)
from planning_rename import rename_planning_file_if_path_changed
from planning_sheet_bootstrap import (
    ensure_planning_sheet_for_new_node,
    remove_planning_sheet_if_present,
)
from roadmap_edit_fields import CODENAME_PATTERN, ID_PATTERN, apply_set
from roadmap_node_keys import new_node_key
from roadmap_load import load_roadmap, validate_roadmap_line_limits
from validate_roadmap import validate_at
from specy_road.runtime_paths import default_user_repo_root


def repo_root(ns: object) -> Path:
    r = getattr(ns, "repo_root", None)
    return Path(r).resolve() if r else default_user_repo_root()


def unknown_node_msg(node_id: str) -> str:
    """User-facing text when a node id is not present in the merged roadmap."""
    return f"no roadmap node with id {node_id!r} (not found in any chunk)"


def run_validate_raise(root: Path) -> None:
    """Run roadmap + registry validation; raise ``ValueError`` with stderr text on failure."""
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        try:
            validate_roadmap_line_limits(root)
            validate_at(root, no_overlap_warn=False, require_registry=True)
        except SystemExit as e:
            if e.code not in (0, None):
                msg = err.getvalue().strip()
                raise ValueError(msg or "validation failed") from e


def run_validate(root: Path) -> None:
    try:
        run_validate_raise(root)
    except ValueError as e:
        print(f"error: validation failed:\n{e}", file=sys.stderr)
        raise SystemExit(1) from e


def node_index_in_chunk(nodes_seq: list, node_id: str) -> int | None:
    for i, item in enumerate(nodes_seq):
        if isinstance(item, dict) and item.get("id") == node_id:
            return i
    return None


def cmd_list(args: object) -> None:
    root = repo_root(args)
    merged = load_roadmap(root)["nodes"]
    chunk_map = build_node_chunk_map(root)
    for n in sorted(merged, key=lambda x: x["id"]):
        nid = n["id"]
        ch = chunk_map.get(nid)
        rel = ch.relative_to(root) if ch else "(unknown)"
        title = str(n.get("title", ""))[:60]
        print(
            f"{nid:12}  {n.get('type', ''):10}  "
            f"{str(n.get('status', '')):12}  {title}  [{rel}]",
        )


def cmd_show(args: object) -> None:
    root = repo_root(args)
    nid = args.node_id
    chunk = find_chunk_path(root, nid)
    if not chunk:
        print(f"error: {unknown_node_msg(nid)}", file=sys.stderr)
        raise SystemExit(1)
    print(f"# chunk: {chunk.relative_to(root)}\n")
    if chunk.suffix.lower() == ".json":
        nodes = load_json_chunk(chunk)
        idx = node_index_in_chunk(nodes, nid)
        if idx is None:
            print(f"error: node {nid!r} not in chunk list", file=sys.stderr)
            raise SystemExit(1)
        json.dump(nodes[idx], sys.stdout, indent=2, sort_keys=True, ensure_ascii=False)
        print()
        return
    print(f"error: unsupported chunk type {chunk.suffix} (expected .json)", file=sys.stderr)
    raise SystemExit(1)


def merged_ids(root: Path) -> set[str]:
    return {n["id"] for n in load_roadmap(root)["nodes"]}


def _resolve_parent(args: object, root: Path) -> object:
    pid = args.parent_id
    if pid in ("null", ""):
        return None
    if pid not in merged_ids(root):
        print(
            f"error: parent_id {pid!r} not found in roadmap",
            file=sys.stderr,
        )
        raise SystemExit(1)
    return pid


def _derive_codename_with_collision_suffix(
    title: str, node_key: str, existing: set[str]
) -> str | None:
    """
    Derive a kebab-case codename from ``title``; if a collision exists,
    append ``-<last 4 hex of node_key>`` to disambiguate (F-006).

    Returns ``None`` when no valid codename can be derived from the title
    (e.g. empty or all-punctuation titles); callers may leave the node
    unnamed so ``validate`` can re-visit it later.
    """
    from roadmap_edit_fields import title_to_codename

    slug = title_to_codename(title)
    if not slug:
        return None
    if slug not in existing:
        return slug
    tail = (node_key or "").replace("-", "")[-4:] or "x"
    cand = f"{slug}-{tail}"
    # Very defensive: extend the tail if still colliding.
    if cand in existing and node_key:
        cand = f"{slug}-{(node_key or '').replace('-', '')[-6:] or 'xx'}"
    return cand


def cmd_add(args: object) -> None:
    root = repo_root(args)
    nid = args.id
    if not ID_PATTERN.match(nid):
        print(f"error: invalid id pattern: {nid!r}", file=sys.stderr)
        raise SystemExit(1)
    if nid in merged_ids(root):
        print(f"error: duplicate node id {nid!r}", file=sys.stderr)
        raise SystemExit(1)
    parent_val = _resolve_parent(args, root)
    if args.codename and not CODENAME_PATTERN.match(args.codename):
        print(f"error: invalid codename: {args.codename!r}", file=sys.stderr)
        raise SystemExit(1)

    node_key = new_node_key()

    # F-006: auto-derive codename from title when not supplied. Codenames are
    # required by downstream pickup and registry logic; forcing users to
    # supply them manually creates the F-006/F-007 friction we are removing.
    codename = args.codename
    if codename is None and args.type == "task":
        existing_codenames = {
            n.get("codename")
            for n in load_roadmap(root)["nodes"]
            if n.get("codename")
        }
        derived = _derive_codename_with_collision_suffix(
            args.title or "", node_key, existing_codenames
        )
        if derived:
            codename = derived
            print(
                f"[heal] node {nid}: codename auto-derived as {derived!r} "
                "from title (see validate for collision rules)",
                file=sys.stderr,
            )

    node: dict = {
        "id": nid,
        "node_key": node_key,
        "parent_id": parent_val,
        "type": args.type,
        "title": args.title,
        "codename": codename,
        "execution_milestone": args.execution_milestone,
        "status": args.status,
        "touch_zones": list(args.touch_zone or []),
        "dependencies": list(args.dependency or []),
        "parallel_tracks": args.parallel_tracks,
    }
    node = {k: v for k, v in node.items() if v is not None}
    if node.get("touch_zones") == []:
        node["touch_zones"] = []
    if node.get("dependencies") == []:
        node["dependencies"] = []

    ensure_planning_sheet_for_new_node(root, node)

    chunk_path = append_node_to_chunk(root, args.chunk, node)
    print(f"[ok] appended node {nid} to {chunk_path.relative_to(root)}")
    run_validate(root)


def append_node_to_chunk(root: Path, chunk_arg: str, node: dict) -> Path:
    chunk_path = resolve_chunk_file(root, chunk_arg)
    if chunk_path.suffix.lower() == ".json":
        nodes = load_json_chunk(chunk_path)
        nodes.append(node)
        write_json_chunk(chunk_path, nodes)
        return chunk_path
    print("error: chunk must be a .json file", file=sys.stderr)
    raise SystemExit(1)


def edit_node_set_pairs(root: Path, node_id: str, pairs: list[tuple[str, str]]) -> None:
    """
    Patch whitelisted fields on a node, save its chunk, and validate.

    Raises ``ValueError`` on missing node, bad keys, or validation failure.
    """
    chunk = find_chunk_path(root, node_id)
    if not chunk:
        raise ValueError(unknown_node_msg(node_id))
    if chunk.suffix.lower() == ".json":
        nodes = load_json_chunk(chunk)
        idx = node_index_in_chunk(nodes, node_id)
        if idx is None:
            raise ValueError(f"node {node_id!r} not found")
        node = nodes[idx]
        if not isinstance(node, dict):
            raise ValueError("corrupt node entry")
        ids = merged_ids(root)
        nkeys = {
            n["node_key"]
            for n in load_roadmap(root)["nodes"]
            if isinstance(n.get("node_key"), str) and n["node_key"]
        }
        for k, v in pairs:
            old_pd = node.get("planning_dir")
            if isinstance(old_pd, str):
                old_pd = old_pd.strip() or None
            apply_set(
                node,
                k,
                v,
                all_ids=ids,
                all_node_keys=nkeys,
                self_id=node_id,
            )
            new_pd = node.get("planning_dir")
            if isinstance(new_pd, str):
                new_pd = new_pd.strip() or None
            rename_planning_file_if_path_changed(root, old_pd, new_pd)
        write_json_chunk(chunk, nodes)
        run_validate_raise(root)
        return
    raise ValueError(f"unsupported chunk type {chunk.suffix} (expected .json)")


def cmd_edit(args: object) -> None:
    root = repo_root(args)
    nid = args.node_id
    pairs: list[tuple[str, str]] = []
    for pair in args.set:
        if "=" not in pair:
            print(f"error: expected key=value, got {pair!r}", file=sys.stderr)
            raise SystemExit(1)
        k, _, v = pair.partition("=")
        pairs.append((k.strip(), v.strip()))
    try:
        edit_node_set_pairs(root, nid, pairs)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        raise SystemExit(1) from None
    chunk = find_chunk_path(root, nid)
    assert chunk is not None
    print(f"[ok] updated {nid} in {chunk.relative_to(root)}")


def can_hard_remove(root: Path, node_id: str) -> tuple[bool, str]:
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
    """Remove a node from its JSON chunk. Raises ``ValueError`` if not found or not removable."""
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
        "(Cancelled was removed from the roadmap schema). "
        "Remove the node with --hard-remove after team agreement, or edit the JSON chunk.",
        file=sys.stderr,
    )
    raise SystemExit(1)
