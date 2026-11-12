"""Roadmap CRUD command implementations (used by roadmap_crud.py), node removal included."""

from __future__ import annotations

import contextlib
import io
import json
import os
import re
import sys
from collections.abc import Callable, Iterator
from pathlib import Path

from specy_road.roadmap_chunk_utils import (
    build_node_chunk_map,
    find_chunk_path,
    load_json_chunk,
    manifest_includes,
)
from specy_road.bundled_scripts.roadmap_chunk_atomic import AtomicWritePlan
from specy_road.planning_artifacts import normalize_planning_dir, resolve_planning_path
from specy_road.planning_sheet_bootstrap import plan_planning_sheet_for_new_node
from specy_road.bundled_scripts.registry_claim_status import (
    leaf_claim_entry,
    list_nodes_json_row,
    list_nodes_status_label,
)
from specy_road.bundled_scripts.registry_claim_zones import claim_zones_following
from specy_road.bundled_scripts.roadmap_crud_prepare import (
    ensure_codename_for_new_node,
    heal_before_mutation,
    next_sibling_order,
)
from specy_road.bundled_scripts.roadmap_crud_chunk_report import (
    NodeChunkWriteReport,
    heal_and_collect_paths,
    plan_add_chunk_writes,
    plan_edit_node_report,
    print_node_chunk_write_report,
    repo_rel,
)
from specy_road.bundled_scripts.roadmap_codename_cap import codename_length_error
from specy_road.bundled_scripts.roadmap_edit_fields import (
    CODENAME_PATTERN,
    ID_PATTERN,
    apply_set,
    merge_set_pairs,
)
from specy_road.bundled_scripts.roadmap_edit_list_fields import planned_test_change_items
from specy_road.roadmap_node_keys import new_node_key
from specy_road.roadmap_layout import natural_id_sort_key
from specy_road.roadmap_gui_lib import registry_by_node_id
from specy_road.roadmap_load import load_roadmap, validate_roadmap_line_limits
from specy_road.bundled_scripts.touch_zone_tracked import warn_written_zones
from specy_road.bundled_scripts.validate_registry_overlap import authoring_overlap_for_node
from specy_road.milestone_review_hold import UNRESOLVABLE_HOLD, held_milestones
from specy_road.validate_roadmap_runner import validate_at
from specy_road.milestone_subtree import structural_leaf_ids
from specy_road.registry_yaml import read_registry, registry_path
from specy_road.runtime_paths import default_user_repo_root
from specy_road.node_kinds import is_gate


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


_VALIDATION_DEFERRED: list[bool] = []  # non-empty inside deferred_validation


@contextlib.contextmanager
def deferred_validation() -> Iterator[None]:
    """Skip :func:`run_validate_raise` in the block: ``apply`` validates its final graph once."""
    _VALIDATION_DEFERRED.append(True)
    try:
        yield
    finally:
        _VALIDATION_DEFERRED.pop()


def run_validate_raise(root: Path) -> None:
    """Run roadmap + registry validation; raise ``ValueError`` with errors on failure."""
    if _VALIDATION_DEFERRED:  # inside deferred_validation, whose caller validates once
        return
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
    """List nodes with status, rollup, and chunk path."""
    root = repo_root(args)
    chunk_map = build_node_chunk_map(root)
    nodes = load_roadmap(root)["nodes"]
    by_reg = registry_by_node_id(read_registry(registry_path(root)))
    leaf_ids = structural_leaf_ids(nodes)
    wanted = {s.lower() for s in (getattr(args, "status", None) or [])}
    rows = []
    for n in sorted(nodes, key=lambda x: natural_id_sort_key(x["id"])):
        rollup = str(n.get("rollup_status") or n.get("status", ""))
        if not wanted or rollup.lower() in wanted:
            ch = chunk_map.get(n["id"])
            claim = leaf_claim_entry(n["id"], leaf_ids=leaf_ids, by_reg=by_reg)
            rows.append((n, rollup, ch.relative_to(root).as_posix() if ch else None, claim))
    # An unresolvable hold leaves the rollup Complete (demote_pending_milestone_rollups),
    # so it is not marked.
    held = {k: v for k, v in held_milestones(root, nodes).items()
            if not v.startswith(UNRESOLVABLE_HOLD)}
    if getattr(args, "as_json", False):
        payload = [{**list_nodes_json_row(n, rel, claim),
                    **({"review_hold": held[n["id"]]} if n["id"] in held else {})}
                   for n, _, rel, claim in rows]
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    print(f"{'ID':12}  {'TYPE':10}  {'STATUS':12}  {'ROLLUP':12}  TITLE  [CHUNK]")
    for n, rollup, rel, claim in rows:
        status = list_nodes_status_label(n, claim)
        rollup += " (review hold)" if n["id"] in held else ""
        print(f"{n['id']:12}  {n.get('type', ''):10}  {status:12}  "
              f"{rollup:12}  {str(n.get('title', ''))[:60]}  [{rel or '(unknown)'}]")


def cmd_show(args: object) -> None:
    root = repo_root(args)
    nid = args.node_id
    chunk = find_chunk_path(root, nid)
    if not chunk:
        print(f"error: {unknown_node_msg(nid)}", file=sys.stderr)
        raise SystemExit(1)
    # stdout stays pure JSON so `show-node | jq` works; the provenance
    # line goes to stderr, where a terminal still shows it.
    print(f"# chunk: {chunk.relative_to(root)}", file=sys.stderr)
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
    # Adding work under an active or pending_mr milestone subtree is a silent
    # scope expansion; same guard as cmd_edit. Root phases (None) pass through.
    if isinstance(parent_val, str) and parent_val.strip():
        _refuse_if_milestone_locked(root, parent_val)
    if args.codename:
        if err := codename_length_error(args.codename):
            print(f"error: {err}", file=sys.stderr)
            raise SystemExit(1)
        if not CODENAME_PATTERN.match(args.codename):
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
        "acceptance": [a.strip() for a in getattr(args, "acceptance", None) or [] if a.strip()]
        or None,
        "planned_test_changes": planned_test_change_items(
            getattr(args, "planned_test_change", None) or []
        ) or None,
        "parallel_tracks": args.parallel_tracks,
        "sensitivity": getattr(args, "sensitivity", None),
        "executor_eligibility": getattr(args, "executor_eligibility", None),
        # Unset sorts as 0 and jumped the pickup queue; append instead.
        "sibling_order": next_sibling_order(root, parent_val, getattr(args, "sibling_order", None)),
    }
    node = {k: v for k, v in node.items() if v is not None}

    from specy_road.bundled_scripts.roadmap_crud_dependency_ops import resolve_dependency_refs
    try:
        node["dependencies"] = resolve_dependency_refs(root, node["dependencies"])
        heal_paths = heal_and_collect_paths(root)
        ensure_codename_for_new_node(root, node)
        parent_id = parent_val if isinstance(parent_val, str) else None
        planned_sheet = plan_planning_sheet_for_new_node(root, node)
        report = plan_add_chunk_writes(
            root,
            parent_id,
            getattr(args, "chunk", None),
            node,
            planned_sheet=planned_sheet,
            extra_paths=heal_paths,
        )
        chunk_path = append_node_to_chunk(root, getattr(args, "chunk", None), node)
    except (ValueError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        raise SystemExit(1) from e
    assert chunk_path.relative_to(root).as_posix() in report.written
    print_node_chunk_write_report(report, verb="appended node")
    warn_written_zones(nid, node.get("touch_zones"), root)


def append_node_to_chunk(
    root: Path, chunk_arg: str | None, node: dict, *, validate: bool = True,
    max_words: int | None = None,
) -> Path:
    """Append ``node`` to a chunk (``chunk_arg`` is a hint); auto-route on overflow.

    Atomic: the planning sheet is staged with the chunk and manifest so a
    validation failure rolls all three back. ``validate=False`` skips the
    post-write check so a batch can validate once after every node is written.
    ``max_words`` caps auto-derived codenames on this write.
    """
    from specy_road.bundled_scripts.roadmap_chunk_router import write_with_routing

    heal_before_mutation(root)
    ensure_codename_for_new_node(root, node, max_words=max_words)
    parent_id_raw = node.get("parent_id")
    parent_id = parent_id_raw if isinstance(parent_id_raw, str) else None
    planned_sheet = plan_planning_sheet_for_new_node(root, node)
    extra = {planned_sheet[0]: planned_sheet[1]} if planned_sheet else None
    with authoring_overlap_for_node(node):
        return write_with_routing(
            root, parent_id, chunk_arg, node, extra_files=extra, validate=validate,
        )


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


def _dependency_set_as_keys(root: Path, raw: str) -> str:
    """Display ids in a ``dependencies`` value become node_keys; a key is unchanged.

    An empty value stays empty, so a clear still removes the field. An unknown
    token raises the ``ValueError`` :func:`resolve_dependency_refs` already uses.
    """
    parts = [p for p in re.split(r"[\s,;]+", raw.strip()) if p]
    if not parts:
        return raw
    from specy_road.bundled_scripts.roadmap_crud_dependency_ops import resolve_dependency_refs

    return " ".join(resolve_dependency_refs(root, parts))


def edit_node_set_pairs(
    root: Path,
    node_id: str,
    pairs: list[tuple[str, str]],
    *,
    sync_codename: bool = False,
    notify: Callable[[str], None] | None = None,
) -> NodeChunkWriteReport:
    """Patch whitelisted fields on a node, then save its chunk atomically."""
    heal_paths = heal_and_collect_paths(root)
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
    # One load feeds both sets: merged_ids() re-read the whole graph to build
    # the ids, and the node_keys comprehension re-read it again on the next line.
    merged = load_roadmap(root)["nodes"]
    ids = {n["id"] for n in merged}
    nkeys = {
        n["node_key"]
        for n in merged
        if isinstance(n.get("node_key"), str) and n["node_key"]
    }
    # Archived node_keys are resolvable too — `validate` accepts them, and
    # every dependency write sends the FULL set. Without this, one archived
    # dependency would make a node's dependencies permanently uneditable.
    nkeys |= _archived_node_keys_quiet(root)
    planning_dir_before = node.get("planning_dir")
    for k, v in pairs:
        if k == "dependencies":
            v = _dependency_set_as_keys(root, v)
        apply_set(
            node,
            k,
            v,
            all_ids=ids,
            all_node_keys=nkeys,
            self_id=node_id,
            sync_codename=sync_codename,
            notify=notify,
        )
    rename = _planning_rename_plan(root, planning_dir_before, node.get("planning_dir"))
    zones = node.get("touch_zones") if any(k == "touch_zones" for k, _ in pairs) else None
    report = plan_edit_node_report(
        root, node_id, chunk, nodes, [rename] if rename else None, zones,
        heal_paths,
    )

    from specy_road.bundled_scripts.roadmap_chunk_router import write_node_update

    with authoring_overlap_for_node(node, node_id=node_id):
        with claim_zones_following(root, node_id, zones, notify=notify):
            holding = write_node_update(
                root, node_id, chunk, nodes, renames=[rename] if rename else None
            )
    holding_rel = repo_rel(root, holding)
    assert holding_rel in report.written
    return report


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
        report = edit_node_set_pairs(
            root,
            nid,
            merge_set_pairs(pairs),
            sync_codename=bool(getattr(args, "sync_codename", False)),
            notify=lambda msg: print(f"[note] {msg}", file=sys.stderr),
        )
    except (ValueError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        raise SystemExit(1) from None
    print_node_chunk_write_report(report, verb="updated")
    if any(k == "touch_zones" for k, _ in pairs):
        edited = next((n for n in load_roadmap(root)["nodes"] if n.get("id") == nid), {})
        warn_written_zones(nid, edited.get("touch_zones"), root)


def cmd_set_gate_status(args: object) -> None:
    root = repo_root(args)
    nid = args.node_id
    _refuse_if_milestone_locked(root, nid)
    nodes = load_roadmap(root)["nodes"]
    target = next((n for n in nodes if n.get("id") == nid), None)
    if target is None:
        print(f"error: {unknown_node_msg(nid)}", file=sys.stderr)
        raise SystemExit(1)
    if not is_gate(target.get("type")):
        print(
            "error: set-gate-status only applies to type gate "
            f"(node {nid!r} is {target.get('type')!r})",
            file=sys.stderr,
        )
        raise SystemExit(1)
    try:
        report = edit_node_set_pairs(root, nid, [("status", args.status)])
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        raise SystemExit(1) from None
    assert report.read_from is not None
    print(f"[ok] gate {nid} status -> {args.status} ({report.read_from})")


# Node removal (``remove-node``, ``archive-node --hard-remove``).
#
# A node and its planning sheet go in one transaction. Unlinking the sheet before
# validating the resulting graph would leave a repo that cannot validate whenever
# the removal is refused (for example because another node still depends on it).
#
# Not to be confused with ``specy-road archive`` (:mod:`specy_road.archive_ops`),
# which moves completed work out of the live graph **reversibly**. The name
# collision is historical.


def _paths_escaping_repo(root: Path, planning_dir: object) -> list[str]:
    """Paths a removal reads or writes that resolve outside the live repository."""
    rels = ["roadmap", "planning", "roadmap/manifest.json",
            registry_path(root).relative_to(root).as_posix()]
    rels += [f"roadmap/{inc}" for inc in manifest_includes(root) if isinstance(inc, str)]
    if isinstance(planning_dir, str) and planning_dir.strip():
        with contextlib.suppress(ValueError):
            rels.append(normalize_planning_dir(planning_dir.strip()))
    live = root.resolve()
    out: list[str] = []
    for rel in rels:
        path = root / rel
        resolved = path.resolve()
        escapes = live != resolved and live not in resolved.parents
        if (path.exists() or path.is_symlink()) and escapes:
            out.append(f"path {rel} resolves outside the repository: {resolved.as_posix()}")
    return out


def remove_node_blockers(root: Path, node_id: str) -> list[str]:
    """Every reason ``node_id`` cannot be removed with ``remove-node`` / hard-remove.

    One containment rule covers every layout: each path the removal reads or
    writes (``roadmap/`` and ``planning/``, the manifest, the registry, every
    included chunk and the node's planning sheet), resolved against the **live**
    repository, must stay inside it; any that escapes is a blocker. Checked
    before any write or dry-run scratch copy, so the rehearsal only ever works on
    already-validated paths.
    """
    nodes = load_roadmap(root)["nodes"]
    target = next((n for n in nodes if n.get("id") == node_id), None)
    if target is None:
        return []
    target_key = target.get("node_key")
    blockers: list[str] = []
    status = target.get("status")
    if status != "Not Started":
        blockers.append(f"node {node_id} status is {status!r}, not 'Not Started'")
    claim = registry_by_node_id(read_registry(registry_path(root))).get(node_id)
    if claim:
        blockers.append(
            "registry claim "
            f"codename {claim.get('codename')!r}, branch {claim.get('branch')!r}"
        )
    for n in nodes:
        if n.get("parent_id") == node_id:
            blockers.append(f"child node {n['id']} has parent_id {node_id!r}")
        if target_key and target_key in (n.get("dependencies") or []):
            blockers.append(f"node {n['id']} depends on node_key of {node_id!r}")
    return blockers + _paths_escaping_repo(root, target.get("planning_dir"))


def can_hard_remove(root: Path, node_id: str) -> tuple[bool, str]:
    """Whether ``node_id`` passes every ``remove-node`` eligibility check."""
    blockers = remove_node_blockers(root, node_id)
    if blockers:
        return False, "\n".join(blockers)
    return True, ""


def planning_sheet_delete_plan(root: Path, planning_dir: object) -> Path | None:
    """Resolve ``planning_dir`` to the sheet to unlink, or ``None`` when there is none."""
    if not isinstance(planning_dir, str) or not planning_dir.strip():
        return None
    try:
        norm = normalize_planning_dir(planning_dir.strip())
    except ValueError:
        return None
    path = resolve_planning_path(root, norm)
    return path if path.is_file() else None


def _scratch_target(resolved: Path, scratch: Path, tops: dict[str, Path]) -> Path | None:
    """Scratch copy of live path ``resolved`` in a copied top, or ``None`` outside them."""
    for name, live_top in tops.items():
        try:
            return scratch / name / resolved.relative_to(live_top)
        except ValueError:
            continue
    return None


def _rebase_graph_symlinks(scratch: Path, live: Path) -> None:
    """Point symlinks in the copied graph trees at their scratch counterparts.

    The copied trees are the top-level folders the scratch root holds as real
    directories (``roadmap/``, ``planning/`` and every planning sheet's top).
    ``copytree(..., symlinks=True)`` keeps links resolving into the live repo, so
    rehearsal would read (and could write) live files, or reject them as outside
    ``roadmap/``. Each link, file or directory, into a live copied tree is
    re-pointed at the same path in the scratch copy, so the layout matches what a
    real run sees. Other links are kept: they resolve outside the scratch
    root, which every chunk lookup, sheet lookup and write rejects, just as a live
    run refuses (or fails validation on) them.
    """
    scratch = scratch.resolve()
    tops = {
        e.name: (live / e.name).resolve()
        for e in scratch.iterdir()
        if e.is_dir() and not e.is_symlink()
    }
    for name in tops:
        for dirpath, dirnames, filenames in os.walk(scratch / name):
            for entry in (*dirnames, *filenames):
                link = Path(dirpath) / entry
                if not link.is_symlink():
                    continue
                resolved = link.resolve()
                if resolved == scratch or scratch in resolved.parents:
                    continue
                dst = _scratch_target(resolved, scratch, tops)
                if dst is not None:
                    link.unlink()
                    link.symlink_to(dst, target_is_directory=resolved.is_dir())


@contextlib.contextmanager
def rehearsal_root(root: Path) -> Iterator[Path]:
    """Throwaway project root for ``--dry-run``: graph trees copied, the rest linked.

    ``apply --dry-run``'s scratch root (same copy/link rule, links into the
    repo's copied trees rebased onto the scratch copy), so rehearsal matches
    real removal on the same layout. The live ``root`` is never written.
    """
    from specy_road.bundled_scripts.roadmap_crud_dependency_ops import _scratch_root

    with _scratch_root(root) as scratch:
        yield scratch


def _commit_remove(root: Path, node_id: str) -> Path | None:
    """Apply one removal on ``root``; return the planning sheet path if any."""
    from specy_road.bundled_scripts.roadmap_chunk_router import validate_callback

    chunk = find_chunk_path(root, node_id)
    if not chunk:
        raise ValueError(unknown_node_msg(node_id))
    if chunk.suffix.lower() != ".json":
        raise ValueError(f"unsupported chunk type {chunk.suffix}")
    nodes = load_json_chunk(chunk)
    idx = node_index_in_chunk(nodes, node_id)
    if idx is None:
        raise ValueError(f"node {node_id!r} not found")
    removed = nodes[idx]
    sheet = planning_sheet_delete_plan(root, removed.get("planning_dir"))
    nodes_after = list(nodes)
    del nodes_after[idx]
    plan = AtomicWritePlan(root=root)
    plan.stage_chunk(chunk, nodes_after)
    if sheet is not None:
        plan.stage_delete(sheet)
    plan.commit(validate_callback(root))
    return sheet


def remove_roadmap_node(root: Path, node_id: str, *, dry_run: bool = False) -> None:
    """Remove a never-started leaf and its planning sheet when nothing blocks it.

    Eligibility is checked first, on the live graph with no self-heal pass,
    before anything is written or copied, so every blocker is reported in both
    modes whatever the layout. That includes the containment rule: every path the
    removal reads or writes must resolve inside the live repository (see
    :func:`remove_node_blockers`); the rehearsal only ever sees validated paths. Real removal
    commits through :class:`~specy_road.bundled_scripts.roadmap_chunk_atomic.AtomicWritePlan`.
    ``--dry-run`` rehearses the same commit on :func:`rehearsal_root` so the live
    tree is not written or unlinked; graph-tree symlinks into the repo are rebased
    onto the scratch copy before rehearsal.

    Raises ``ValueError`` if not found, not removable, or if the resulting graph
    fails validation.
    """
    blockers = remove_node_blockers(root, node_id)
    if blockers:
        raise ValueError("\n".join(blockers))
    if not dry_run:
        _commit_remove(root, node_id)
        return
    with rehearsal_root(root) as scratch:
        sheet = _commit_remove(scratch, node_id)
        shown = sheet.relative_to(scratch.resolve()).as_posix() if sheet else "(none)"
    print(f"would remove node {node_id}")
    print(f"planning sheet: {shown}")


def delete_roadmap_node_hard(root: Path, node_id: str) -> None:
    """Backward-compatible alias for :func:`remove_roadmap_node` (no dry-run)."""
    remove_roadmap_node(root, node_id, dry_run=False)


def _exit_on_value_error(fn: object, *args: object, **kwargs: object) -> None:
    try:
        fn(*args, **kwargs)  # type: ignore[operator]
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        raise SystemExit(1) from None


def cmd_remove_node(args: object) -> None:
    root = repo_root(args)
    nid = args.node_id
    dry_run = bool(getattr(args, "dry_run", False))
    _exit_on_value_error(remove_roadmap_node, root, nid, dry_run=dry_run)
    if not dry_run:
        print(f"[ok] removed {nid}")


def cmd_archive(args: object) -> None:
    root = repo_root(args)
    nid = args.node_id
    if args.hard_remove:
        _exit_on_value_error(remove_roadmap_node, root, nid, dry_run=False)
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
