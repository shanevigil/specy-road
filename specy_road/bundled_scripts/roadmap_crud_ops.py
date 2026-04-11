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
from roadmap_edit_fields import CODENAME_PATTERN, ID_PATTERN, apply_set
from roadmap_node_keys import new_node_key
from roadmap_load import load_roadmap, validate_roadmap_line_limits
from validate_roadmap import validate_at

from specy_road.runtime_paths import default_user_repo_root


def repo_root(ns: object) -> Path:
    r = getattr(ns, "repo_root", None)
    return Path(r).resolve() if r else default_user_repo_root()


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
        print(f"error: no chunk contains node {nid!r}", file=sys.stderr)
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


def _checklist_citation(ns: object) -> str | None:
    cc = getattr(ns, "contract_citation", None)
    if cc is not None and str(cc).strip():
        return str(cc).strip()
    return None


def parse_checklist_flags(ns: object) -> dict | None:
    cite = _checklist_citation(ns)
    fields = (
        ns.artifact_action,
        cite,
        ns.interface_contract,
        ns.constraints_note,
        ns.dependency_note,
    )
    if all(x is None for x in fields):
        return None
    if any(x is None or not str(x).strip() for x in fields):
        print(
            "error: agentic checklist requires all five of: "
            "--artifact-action, --contract-citation, "
            "--interface-contract, --constraints-note, --dependency-note",
            file=sys.stderr,
        )
        raise SystemExit(1)
    return {
        "artifact_action": ns.artifact_action.strip(),
        "contract_citation": cite or "",
        "interface_contract": ns.interface_contract.strip(),
        "constraints_note": ns.constraints_note.strip(),
        "dependency_note": ns.dependency_note.strip(),
    }


def _checklist_from_json(raw: str) -> dict:
    try:
        checklist = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"error: invalid --checklist-json: {e}", file=sys.stderr)
        raise SystemExit(1) from e
    cite = checklist.get("contract_citation")
    merged = {
        "artifact_action": checklist.get("artifact_action"),
        "contract_citation": cite,
        "interface_contract": checklist.get("interface_contract"),
        "constraints_note": checklist.get("constraints_note"),
        "dependency_note": checklist.get("dependency_note"),
    }
    for k, v in merged.items():
        if not v or not str(v).strip():
            print(f"error: checklist missing or empty {k!r}", file=sys.stderr)
            raise SystemExit(1)
    return merged


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


def _resolve_checklist_for_add(args: object) -> dict | None:
    if args.checklist_json:
        return _checklist_from_json(args.checklist_json)
    if args.execution_subtask == "agentic":
        cl = parse_checklist_flags(args)
        if cl is None:
            print(
                "error: execution_subtask agentic requires full checklist "
                "(five flags or --checklist-json)",
                file=sys.stderr,
            )
            raise SystemExit(1)
        return cl
    return None


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

    checklist = _resolve_checklist_for_add(args)
    if checklist is not None and args.execution_subtask != "agentic":
        print(
            "error: checklist only allowed with --execution-subtask agentic",
            file=sys.stderr,
        )
        raise SystemExit(1)

    node: dict = {
        "id": nid,
        "node_key": new_node_key(),
        "parent_id": parent_val,
        "type": args.type,
        "title": args.title,
        "codename": args.codename,
        "execution_milestone": args.execution_milestone,
        "execution_subtask": args.execution_subtask,
        "status": args.status,
        "touch_zones": list(args.touch_zone or []),
        "dependencies": list(args.dependency or []),
        "parallel_tracks": args.parallel_tracks,
    }
    if checklist is not None:
        node["agentic_checklist"] = checklist
    node = {k: v for k, v in node.items() if v is not None}
    if node.get("touch_zones") == []:
        node["touch_zones"] = []
    if node.get("dependencies") == []:
        node["dependencies"] = []

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
        raise ValueError(f"no chunk contains node {node_id!r}")
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
            apply_set(
                node,
                k,
                v,
                all_ids=ids,
                all_node_keys=nkeys,
                self_id=node_id,
            )
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
        raise SystemExit(1) from e
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


def _archive_apply(
    nodes: list,
    idx: int,
    nid: str,
    chunk: Path,
    root: Path,
    *,
    hard_remove: bool,
) -> None:
    if hard_remove:
        ok, msg = can_hard_remove(root, nid)
        if not ok:
            print(f"error: cannot hard-remove: {msg}", file=sys.stderr)
            raise SystemExit(1)
        del nodes[idx]
        print(f"[ok] removed {nid} from {chunk.relative_to(root)}")
    else:
        node = nodes[idx]
        if isinstance(node, dict):
            node["status"] = "Cancelled"
        print(f"[ok] status -> Cancelled for {nid}")


def cmd_archive(args: object) -> None:
    root = repo_root(args)
    nid = args.node_id
    chunk = find_chunk_path(root, nid)
    if not chunk:
        print(f"error: no chunk contains node {nid!r}", file=sys.stderr)
        raise SystemExit(1)
    if chunk.suffix.lower() == ".json":
        nodes = load_json_chunk(chunk)
        idx = node_index_in_chunk(nodes, nid)
        if idx is None:
            print(f"error: node {nid!r} not found", file=sys.stderr)
            raise SystemExit(1)
        _archive_apply(nodes, idx, nid, chunk, root, hard_remove=args.hard_remove)
        write_json_chunk(chunk, nodes)
        run_validate(root)
        return
    print(f"error: unsupported chunk type {chunk.suffix}", file=sys.stderr)
    raise SystemExit(1)
