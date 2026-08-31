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
)
from planning_artifacts import normalize_planning_dir, resolve_planning_path
from planning_sheet_bootstrap import plan_planning_sheet_for_new_node
from roadmap_crud_prepare import ensure_codename_for_new_node, heal_before_mutation
from roadmap_edit_fields import CODENAME_PATTERN, ID_PATTERN, apply_set
from roadmap_node_keys import new_node_key
from roadmap_layout import natural_id_sort_key
from roadmap_load import load_roadmap, validate_roadmap_line_limits
from validate_roadmap import validate_at
from specy_road.runtime_paths import default_user_repo_root


def repo_root(ns: object) -> Path:
    r = getattr(ns, "repo_root", None)
    return Path(r).resolve() if r else default_user_repo_root()


def unknown_node_msg(node_id: str) -> str:
    """User-facing text when a node id is not present in the merged roadmap."""
    return f"no roadmap node with id {node_id!r} (not found in any chunk)"


def _refuse_if_milestone_locked(root: Path, node_id: str) -> None:
    """Print the lock error and raise SystemExit(1) if ``node_id`` is locked.

    Centralizes the cmd_add / cmd_edit / cmd_set_gate_status pre-mutation
    guard so the lock contract has one place to maintain.
    """
    from specy_road.milestone_lock import assert_pm_nodes_not_milestone_locked

    nodes = load_roadmap(root)["nodes"]
    try:
        assert_pm_nodes_not_milestone_locked(nodes, node_id)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        raise SystemExit(1) from e


def _archived_node_keys_quiet(root: Path) -> set[str]:
    """Archived keys, or empty when the ledger is absent/unreadable."""
    try:
        from specy_road.archive_index import archived_node_keys

        return archived_node_keys(root)
    except Exception:  # noqa: BLE001 - editing must not depend on the ledger
        return set()


def run_validate_raise(root: Path) -> None:
    """Run roadmap + registry validation; raise ``ValueError`` with the errors on failure.

    Both streams are captured: validation's ``OK: roadmap and registry
    validate.`` would otherwise interleave with each mutation command's own
    ``[ok]`` line, reading as if the command reported twice. Warnings pass
    through as warnings rather than being folded into the raised message, so a
    caller printing ``error: {message}`` does not relabel them.
    """
    err = io.StringIO()
    out = io.StringIO()
    failed = False
    with contextlib.redirect_stderr(err), contextlib.redirect_stdout(out):
        try:
            validate_roadmap_line_limits(root)
            validate_at(
                root,
                no_overlap_warn=False,
                require_registry=True,
                auto_heal=False,
            )
        except SystemExit as e:
            failed = e.code not in (0, None)
    lines = [ln for ln in err.getvalue().splitlines() if ln.strip()]
    for line in (ln for ln in lines if "warning" in ln.lower()):
        print(line, file=sys.stderr)
    if failed:
        errors = [ln for ln in lines if "warning" not in ln.lower()]
        raise ValueError("\n".join(errors) or "validation failed")


def node_index_in_chunk(nodes_seq: list, node_id: str) -> int | None:
    for i, item in enumerate(nodes_seq):
        if isinstance(item, dict) and item.get("id") == node_id:
            return i
    return None


def cmd_list(args: object) -> None:
    """List nodes with both statuses.

    ``STATUS`` is the node's own field as written in the chunk; ``ROLLUP`` is
    what ``roadmap.md`` and the PM GUI show (a parent rolls up from its leaf
    descendants). One unlabelled column let the two disagree silently.
    """
    root = repo_root(args)
    merged = load_roadmap(root)["nodes"]
    chunk_map = build_node_chunk_map(root)
    print(f"{'ID':12}  {'TYPE':10}  {'STATUS':12}  {'ROLLUP':12}  TITLE  [CHUNK]")
    for n in sorted(merged, key=lambda x: natural_id_sort_key(x["id"])):
        nid = n["id"]
        ch = chunk_map.get(nid)
        rel = ch.relative_to(root) if ch else "(unknown)"
        title = str(n.get("title", ""))[:60]
        own = str(n.get("status", ""))
        rollup = str(n.get("rollup_status") or own)
        print(
            f"{nid:12}  {n.get('type', ''):10}  "
            f"{own:12}  {rollup:12}  {title}  [{rel}]",
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
    # Refuse to add a node under a parent that lives inside an active or
    # pending_mr milestone subtree — adding new work mid-milestone is a
    # silent scope expansion. Mirrors the cmd_edit / cmd_set_gate_status
    # guards. The check fires only when the parent is a real node (root
    # phases pass through with parent_val=None).
    if isinstance(parent_val, str) and parent_val.strip():
        _refuse_if_milestone_locked(root, parent_val)
    if args.codename and not CODENAME_PATTERN.match(args.codename):
        print(f"error: invalid codename: {args.codename!r}", file=sys.stderr)
        raise SystemExit(1)

    node_key = new_node_key()

    node: dict = {
        "id": nid,
        "node_key": node_key,
        "parent_id": parent_val,
        "type": args.type,
        "title": args.title,
        "codename": args.codename,
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

    try:
        chunk_path = append_node_to_chunk(root, getattr(args, "chunk", None), node)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        raise SystemExit(1) from e
    print(f"[ok] appended node {nid} to {chunk_path.relative_to(root)}")


def append_node_to_chunk(root: Path, chunk_arg: str | None, node: dict) -> Path:
    """Append ``node`` to a roadmap chunk, auto-routing if the hint chunk would overflow.

    ``chunk_arg`` is treated as a *hint*: if supplied and the chunk has room,
    the node lands there (today's behavior). If no hint or the hint is full,
    the chunk router picks a same-phase chunk, then any chunk, then auto-creates
    a new chunk and updates the manifest.

    Atomic: the node's planning sheet is staged alongside the chunk and manifest,
    so a validation failure rolls back all three. Scaffolding the sheet outside
    the transaction used to leave an orphan behind that ``validate`` rejects,
    turning a refused ``add-node`` into a repo that cannot validate at all.
    """
    from roadmap_chunk_router import write_with_routing

    heal_before_mutation(root)
    ensure_codename_for_new_node(root, node)
    parent_id_raw = node.get("parent_id")
    parent_id = parent_id_raw if isinstance(parent_id_raw, str) else None
    planned_sheet = plan_planning_sheet_for_new_node(root, node)
    extra = {planned_sheet[0]: planned_sheet[1]} if planned_sheet else None
    return write_with_routing(root, parent_id, chunk_arg, node, extra_files=extra)


def _planning_rename_plan(
    root: Path, old_rel: object, new_rel: object
) -> tuple[Path, Path] | None:
    """Resolve a ``planning_dir`` change into a ``(src, dst)`` move, or ``None``.

    Same guards the eager rename applied: both sides must be normalizable
    planning paths, the source must exist, and the destination must be free.
    """
    if not isinstance(old_rel, str) or not isinstance(new_rel, str):
        return None
    if not old_rel.strip() or not new_rel.strip():
        return None
    try:
        old_norm = normalize_planning_dir(old_rel.strip())
        new_norm = normalize_planning_dir(new_rel.strip())
    except ValueError:
        return None
    if old_norm == new_norm:
        return None
    src = resolve_planning_path(root, old_norm)
    dst = resolve_planning_path(root, new_norm)
    if not src.is_file() or dst.exists():
        return None
    return src, dst


def edit_node_set_pairs(root: Path, node_id: str, pairs: list[tuple[str, str]]) -> None:
    """
    Patch whitelisted fields on a node, then save its chunk atomically.

    Nothing reaches disk until the whole prospective graph validates: the chunk
    write, any overflow relocation, and any planning-sheet rename are staged
    together. Writing first and validating afterwards left a rejected edit — and
    a half-renamed planning sheet — on disk, which blocked every later command
    and made a multi-``--set`` batch impossible to reason about.

    Raises ``ValueError`` on missing node, bad keys, or validation failure.
    """
    heal_before_mutation(root)
    chunk = find_chunk_path(root, node_id)
    if not chunk:
        raise ValueError(unknown_node_msg(node_id))
    if chunk.suffix.lower() != ".json":
        raise ValueError(f"unsupported chunk type {chunk.suffix} (expected .json)")
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
    # Archived node_keys are resolvable too — `validate` accepts them, and
    # every dependency write sends the FULL set. Without this, one archived
    # dependency would make a node's dependencies permanently uneditable.
    nkeys |= _archived_node_keys_quiet(root)
    planning_dir_before = node.get("planning_dir")
    for k, v in pairs:
        apply_set(
            node,
            k,
            v,
            all_ids=ids,
            all_node_keys=nkeys,
            self_id=node_id,
        )
    rename = _planning_rename_plan(root, planning_dir_before, node.get("planning_dir"))

    from roadmap_chunk_router import write_node_update

    write_node_update(
        root,
        node_id,
        chunk,
        nodes,
        renames=[rename] if rename else None,
    )


def cmd_edit(args: object) -> None:
    root = repo_root(args)
    nid = args.node_id
    _refuse_if_milestone_locked(root, nid)
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


def cmd_set_gate_status(args: object) -> None:
    root = repo_root(args)
    nid = args.node_id
    _refuse_if_milestone_locked(root, nid)
    nodes = load_roadmap(root)["nodes"]
    target = next((n for n in nodes if n.get("id") == nid), None)
    if target is None:
        print(f"error: {unknown_node_msg(nid)}", file=sys.stderr)
        raise SystemExit(1)
    if target.get("type") != "gate":
        print(
            "error: set-gate-status only applies to type gate "
            f"(node {nid!r} is {target.get('type')!r})",
            file=sys.stderr,
        )
        raise SystemExit(1)
    try:
        edit_node_set_pairs(root, nid, [("status", args.status)])
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        raise SystemExit(1) from None
    chunk = find_chunk_path(root, nid)
    assert chunk is not None
    print(f"[ok] gate {nid} status -> {args.status} ({chunk.relative_to(root)})")


# Node removal lives in ``roadmap_crud_delete`` (per-file line cap). Re-exported
# here so ``roadmap_crud_argparse``, the PM GUI routes, and tests keep one
# import site. Imported at the bottom because that module imports back for
# ``node_index_in_chunk`` / ``repo_root`` / ``unknown_node_msg``.
from roadmap_crud_delete import (  # noqa: E402,F401
    can_hard_remove,
    cmd_archive,
    delete_roadmap_node_hard,
)
