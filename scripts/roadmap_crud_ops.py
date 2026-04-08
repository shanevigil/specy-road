"""Roadmap CRUD command implementations (used by roadmap_crud.py)."""

from __future__ import annotations

import contextlib
import io
import json
import re
import sys
from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedSeq

from roadmap_chunk_utils import (
    build_node_chunk_map,
    find_chunk_path,
    resolve_chunk_file,
)
from roadmap_load import load_roadmap, validate_roadmap_yaml_line_limits
from validate_roadmap import validate_at

ROOT_DEFAULT = Path(__file__).resolve().parent.parent

ID_PATTERN = re.compile(r"^M[0-9]+(\.[0-9]+)*$")
CODENAME_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

EDIT_WHITELIST = frozenset({
    "status",
    "title",
    "codename",
    "execution_milestone",
    "execution_subtask",
    "parallel_tracks",
    "notes",
    "goal",
    "agentic_checklist.artifact_action",
    "agentic_checklist.spec_citation",
    "agentic_checklist.interface_contract",
    "agentic_checklist.constraints_note",
    "agentic_checklist.dependency_note",
})


def repo_root(ns: object) -> Path:
    r = getattr(ns, "repo_root", None)
    return Path(r).resolve() if r else ROOT_DEFAULT


def run_validate_raise(root: Path) -> None:
    """Run roadmap + registry validation; raise ``ValueError`` with stderr text on failure."""
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        try:
            validate_roadmap_yaml_line_limits(root)
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


def load_yaml_document(path: Path) -> tuple[object, YAML]:
    text = path.read_text(encoding="utf-8")
    y = YAML()
    y.preserve_quotes = True
    y.indent(mapping=2, sequence=4, offset=2)
    return y.load(text), y


def save_yaml_document(path: Path, data: object, y: YAML) -> None:
    with path.open("w", encoding="utf-8") as f:
        y.dump(data, f)


def node_index_in_chunk(nodes_seq: object, node_id: str) -> int | None:
    if not isinstance(nodes_seq, (list, CommentedSeq)):
        return None
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
    data, y = load_yaml_document(chunk)
    if not isinstance(data, dict) or "nodes" not in data:
        print(f"error: invalid chunk structure in {chunk}", file=sys.stderr)
        raise SystemExit(1)
    idx = node_index_in_chunk(data["nodes"], nid)
    if idx is None:
        print(f"error: node {nid!r} not in chunk list", file=sys.stderr)
        raise SystemExit(1)
    node = data["nodes"][idx]
    print(f"# chunk: {chunk.relative_to(root)}\n")
    y.dump(node, sys.stdout)


def merged_ids(root: Path) -> set[str]:
    return {n["id"] for n in load_roadmap(root)["nodes"]}


def parse_checklist_flags(ns: object) -> dict | None:
    fields = (
        ns.artifact_action,
        ns.spec_citation,
        ns.interface_contract,
        ns.constraints_note,
        ns.dependency_note,
    )
    if all(x is None for x in fields):
        return None
    if any(x is None or not str(x).strip() for x in fields):
        print(
            "error: agentic checklist requires all five of: "
            "--artifact-action, --spec-citation, --interface-contract, "
            "--constraints-note, --dependency-note",
            file=sys.stderr,
        )
        raise SystemExit(1)
    return {
        "artifact_action": ns.artifact_action.strip(),
        "spec_citation": ns.spec_citation.strip(),
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
    for k in (
        "artifact_action",
        "spec_citation",
        "interface_contract",
        "constraints_note",
        "dependency_note",
    ):
        if not checklist.get(k) or not str(checklist[k]).strip():
            print(f"error: checklist missing or empty {k!r}", file=sys.stderr)
            raise SystemExit(1)
    return checklist


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
    data, y = load_yaml_document(chunk_path)
    if not isinstance(data, dict) or "nodes" not in data:
        print("error: chunk must contain top-level `nodes` list", file=sys.stderr)
        raise SystemExit(1)
    nodes_seq = data["nodes"]
    if not isinstance(nodes_seq, (list, CommentedSeq)):
        print("error: `nodes` must be a list", file=sys.stderr)
        raise SystemExit(1)
    nodes_seq.append(node)
    save_yaml_document(chunk_path, data, y)
    return chunk_path


def apply_set(node: dict, dotted_key: str, raw_val: str) -> None:
    if dotted_key not in EDIT_WHITELIST:
        raise ValueError(f"key not allowed for --set: {dotted_key!r}")
    parts = dotted_key.split(".")
    if len(parts) == 1:
        key = parts[0]
        if key == "parallel_tracks":
            try:
                node[key] = int(raw_val)
            except ValueError as e:
                raise ValueError(
                    f"parallel_tracks must be an integer, got {raw_val!r}",
                ) from e
        elif key == "codename" and raw_val.lower() in ("null", "~", ""):
            node[key] = None
        elif key == "execution_milestone" and raw_val.lower() in ("null", "~", ""):
            node[key] = None
        elif key == "execution_subtask" and raw_val.lower() in ("null", "~", ""):
            node[key] = None
        else:
            node[key] = raw_val
        return
    if parts[0] != "agentic_checklist" or len(parts) != 2:
        raise ValueError(f"unsupported nested key: {dotted_key!r}")
    sub = parts[1]
    ac = node.get("agentic_checklist")
    if not isinstance(ac, dict):
        ac = {}
        node["agentic_checklist"] = ac
    ac[sub] = raw_val


def edit_node_set_pairs(root: Path, node_id: str, pairs: list[tuple[str, str]]) -> None:
    """
    Patch whitelisted fields on a node, save its chunk, and validate.

    Raises ``ValueError`` on missing node, bad keys, or validation failure.
    """
    chunk = find_chunk_path(root, node_id)
    if not chunk:
        raise ValueError(f"no chunk contains node {node_id!r}")
    data, y = load_yaml_document(chunk)
    idx = node_index_in_chunk(data["nodes"], node_id)
    if idx is None:
        raise ValueError(f"node {node_id!r} not found")
    node = data["nodes"][idx]
    if not isinstance(node, dict):
        raise ValueError("corrupt node entry")
    for k, v in pairs:
        apply_set(node, k, v)
    save_yaml_document(chunk, data, y)
    run_validate_raise(root)


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
    for n in load_roadmap(root)["nodes"]:
        if n.get("parent_id") == node_id:
            return False, f"child node {n['id']} has parent_id {node_id!r}"
        if node_id in (n.get("dependencies") or []):
            return False, f"node {n['id']} depends on {node_id!r}"
    return True, ""


def cmd_archive(args: object) -> None:
    root = repo_root(args)
    nid = args.node_id
    chunk = find_chunk_path(root, nid)
    if not chunk:
        print(f"error: no chunk contains node {nid!r}", file=sys.stderr)
        raise SystemExit(1)
    data, y = load_yaml_document(chunk)
    nodes_seq = data.get("nodes")
    idx = node_index_in_chunk(nodes_seq, nid)
    if idx is None:
        print(f"error: node {nid!r} not found", file=sys.stderr)
        raise SystemExit(1)

    if args.hard_remove:
        ok, msg = can_hard_remove(root, nid)
        if not ok:
            print(f"error: cannot hard-remove: {msg}", file=sys.stderr)
            raise SystemExit(1)
        del nodes_seq[idx]
        print(f"[ok] removed {nid} from {chunk.relative_to(root)}")
    else:
        node = nodes_seq[idx]
        if isinstance(node, dict):
            node["status"] = "Cancelled"
        print(f"[ok] status -> Cancelled for {nid}")
    save_yaml_document(chunk, data, y)
    run_validate(root)
