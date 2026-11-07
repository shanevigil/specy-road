"""Roadmap dependency CRUD for the CLI (same edit path as the PM GUI patch).

Also ``apply``: a file of ``add-node`` / ``edit-node`` / ``add-dependency``
changes, and the restructure commands (``move-node``, ``group-nodes``,
``indent``, ``outdent``, ``remove-node``, ``archive``), run as one batch. It lives here because a batch is mostly dependency
wiring between nodes it creates, which is why dependencies accept display ids.
"""

from __future__ import annotations

import contextlib
import io
import os
import shutil
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path

from specy_road.bundled_scripts.roadmap_chunk_utils import find_chunk_path
from specy_road.bundled_scripts.roadmap_crud_ops import (
    deferred_validation,
    edit_node_set_pairs,
    repo_root,
    run_validate_raise,
    unknown_node_msg,
)
from specy_road.bundled_scripts.roadmap_apply_entries import id_map_lines, parse_change_file
from specy_road.bundled_scripts.planning_artifacts import normalize_planning_dir
from specy_road.bundled_scripts.effective_dependency_checks import newly_waiting_suffix
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


def resolve_dependency_refs(root: Path, refs: list[str]) -> list[str]:
    """The node_keys ``refs`` name: a node_key as given, a display id as its key.

    Only keys are stored, because ``move-node`` renumbers display ids. Ids are
    accepted so a caller need not look keys up first — and a batch that adds a
    node cannot know its key until the node exists.
    """
    nodes = load_roadmap(root)["nodes"]
    keys = {n["node_key"] for n in nodes if n.get("node_key")} | _archived_keys(root)
    by_id = {n.get("id"): n.get("node_key") for n in nodes}
    out: list[str] = []
    for raw in refs:
        ref = str(raw).strip()
        if ref in keys:
            out.append(ref)
        elif by_id.get(ref):
            out.append(by_id[ref])
        else:
            raise ValueError(
                f"dependency {ref!r} is neither a node id nor a node_key in the roadmap"
            )
    return out


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
    rec = merged_node_by_id(root, nid)
    if not rec:
        print(f"error: {unknown_node_msg(nid)}", file=sys.stderr)
        raise SystemExit(1)
    try:
        [dep_key] = resolve_dependency_refs(root, [args.dep_node_key])
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        raise SystemExit(1) from None
    cur = [str(x) for x in (rec.get("dependencies") or []) if x]
    if dep_key in cur:
        print(f"[ok] {nid} already lists dependency {dep_key!r}")
        return
    cur.append(dep_key)
    waits = newly_waiting_suffix(load_roadmap(root)["nodes"], nid, dep_key)
    try:
        edit_node_set_pairs(
            root, nid, [("dependencies", _dependencies_patch_value(cur))]
        )
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        raise SystemExit(1) from None
    chunk = find_chunk_path(root, nid)
    assert chunk is not None
    print(f"[ok] added {dep_key!r} to {nid} in {chunk.relative_to(root)}{waits}")


def _refuse_unlisted_dependency(root: Path, nid: str, ref: str, cur: list[str]) -> None:
    """Exit 1 naming what ``nid`` does depend on, so the caller can pick the right one."""
    ids = {n.get("node_key"): n.get("id") for n in load_roadmap(root)["nodes"]}
    listed = ", ".join(f"{ids.get(k) or '?'} ({k})" for k in cur) or "none"
    print(f"error: {nid} does not list dependency {ref!r}; its dependencies: {listed}.", file=sys.stderr)
    print(f"  See them with `specy-road list-dependencies {nid}`, then retry with one listed there.",
          file=sys.stderr)
    raise SystemExit(1)


def cmd_remove_dependency(args: object) -> None:
    root = repo_root(args)
    nid = args.node_id
    rec = merged_node_by_id(root, nid)
    if not rec:
        print(f"error: {unknown_node_msg(nid)}", file=sys.stderr)
        raise SystemExit(1)
    cur = [str(x) for x in (rec.get("dependencies") or []) if x]
    ref = args.dep_node_key
    try:   # a listed key the roadmap no longer has stays removable by that key
        dep_key = ref if ref in cur else resolve_dependency_refs(root, [ref])[0]
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        print(f"  See what {nid} depends on with `specy-road list-dependencies {nid}`.", file=sys.stderr)
        raise SystemExit(1) from None
    if dep_key not in cur:
        _refuse_unlisted_dependency(root, nid, ref, cur)
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


# ---------------------------------------------------------------------------
# apply: a change file as one batch
# ---------------------------------------------------------------------------

def _run_changes(changes: list[object], root: Path) -> str:
    """Run each change's command in order, then validate the final graph once.

    The first refusal stops the batch. Per-command validation is deferred
    (``deferred_validation``): an intermediate graph may be invalid, only the
    last one has to validate. Returns the commands' ``[ok]`` lines, held back
    until the batch validates: printed as they happened, a refused batch would
    still list ``[ok]`` for changes it then rolled back. Errors go to stderr
    and are not held.
    """
    out = io.StringIO()
    with contextlib.redirect_stdout(out), deferred_validation():
        for i, ns in enumerate(changes, 1):
            ns.repo_root = root
            try:
                code = ns.func(ns)  # archive returns its exit code; the rest exit
            except SystemExit as e:
                code = e.code
            except ValueError as e:
                print(f"error: {e}", file=sys.stderr)
                code = 1
            if code not in (0, None):
                raise ValueError(
                    f"change {i} ({ns.apply_op}) failed; no change in the batch was applied"
                )
    try:
        run_validate_raise(root)
    except ValueError as e:
        raise ValueError(
            f"the batch's resulting roadmap does not validate; no change in the batch was applied\n{e}"
        ) from None
    return out.getvalue()


def _graph_paths(root: Path) -> list[Path]:
    """What a graph edit can write: ``roadmap/`` and every planning sheet's top folder."""
    tops = {"roadmap", "planning"}
    for n in load_roadmap(root)["nodes"]:
        try:
            tops.add(normalize_planning_dir(str(n.get("planning_dir") or "")).split("/")[0])
        except ValueError:
            continue
    return [root / t for t in sorted(tops)]


def _batch_paths(root: Path) -> list[Path]:
    """What a batch can write: the graph paths, plus ``roadmap.md`` and the
    digest that ``archive`` regenerates."""
    from specy_road.generated_files import GENERATED_COMMITTED

    return _graph_paths(root) + [root / name for name in GENERATED_COMMITTED]


def _files_under(paths: list[Path]) -> list[Path]:
    out: list[Path] = []
    for p in paths:
        if p.is_file():
            out.append(p)
        elif p.is_dir():
            out.extend(f for f in p.rglob("*") if f.is_file())
    return out


def _dirs_under(paths: list[Path]) -> set[Path]:
    return {d for p in paths if p.is_dir() for d in [p, *p.rglob("*")] if d.is_dir()}


def _snapshot(paths: list[Path], root: Path) -> dict[Path, bytes | str]:
    """Each file under ``paths`` as its bytes, each link to a file as its text.

    An archive moves a linked sheet's target and unlinks the link, so a target
    in the repo is kept too, wherever it is. One outside the repo is never
    moved (the archive refuses it) and never written back.
    """
    out: dict[Path, bytes | str] = {}
    for f in _files_under(paths):
        if f.is_symlink():
            out[f] = os.readlink(f)
            target = f.resolve()
            if target.is_relative_to(root.resolve()):
                out[target] = target.read_bytes()
        else:
            out[f] = f.read_bytes()
    return out


def _restore(paths: list[Path], before: dict[Path, bytes | str], dirs: set[Path]) -> None:
    """Put ``paths`` back as they were: drop new files, rewrite changed ones, recreate links as links.

    Folders the batch created (``roadmap/archive/`` on a first archive) go too,
    once emptied; ``dirs`` are the ones that were there before.
    """
    for f in _files_under(paths):
        if f not in before:
            f.unlink()
    for f, was in before.items():
        if isinstance(was, str):
            if not f.is_symlink() or os.readlink(f) != was:
                f.unlink(missing_ok=True)
                f.parent.mkdir(parents=True, exist_ok=True)
                f.symlink_to(was)
        elif not f.is_file() or f.read_bytes() != was:
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(was)
    for d in sorted(_dirs_under(paths) - dirs, key=lambda d: len(d.parts), reverse=True):
        if not any(d.iterdir()):
            d.rmdir()


def _apply_in_place(changes: list[object], root: Path) -> str:
    """Run the batch all or nothing.

    Each command commits its own transaction, so the batch holds a snapshot of
    everything they can write and restores it if any one refuses or the final
    graph does not validate.
    """
    paths = _batch_paths(root)
    before = _snapshot(paths, root)
    dirs = _dirs_under(paths)
    try:
        return _run_changes(changes, root)
    except BaseException:
        _restore(paths, before, dirs)
        raise


@contextlib.contextmanager
def _scratch_root(root: Path) -> Iterator[Path]:
    """A throwaway root to rehearse in: graph files copied, the rest linked.

    The rehearsal runs the same commands as a real apply, so it needs somewhere
    to write. What a batch writes (``_batch_paths``) is copied; schemas,
    constraints and the source tree (touch-zone checks read it) are symlinked; ``.git`` is left out so nothing can reach the real index.
    Links in the copied trees that point into the repo are rebased onto the
    copy (:func:`_rebase_graph_symlinks`), so no rehearsal reads or writes a
    live file and every rehearsal sees the layout a real run writes.
    """
    from specy_road.bundled_scripts.roadmap_crud_delete import _rebase_graph_symlinks

    copied = {p.name for p in _batch_paths(root)}
    with tempfile.TemporaryDirectory(prefix="specy-road-apply-") as tmp:
        scratch = Path(tmp)
        for entry in root.iterdir():
            dst = scratch / entry.name
            if entry.name == ".git":
                continue
            if entry.name not in copied:
                try:
                    dst.symlink_to(entry, target_is_directory=entry.is_dir())
                    continue
                except OSError:
                    pass  # no symlink privilege (Windows): copy instead
            if entry.is_dir():
                shutil.copytree(entry, dst, symlinks=True)
            else:
                shutil.copy2(entry, dst)
        _rebase_graph_symlinks(scratch, root.resolve())
        yield scratch


def wave_preview(root: Path) -> list[str]:
    """Ready / waves / blocked for the graph under ``root``, as ``grind-session --plan`` computes them."""
    from specy_road.bundled_scripts.planning_sheet_bootstrap import unauthored_leaves
    from specy_road.bundled_scripts.session_plan import compute_session_plan
    from specy_road.registry_yaml import read_registry, registry_path

    nodes = load_roadmap(root)["nodes"]
    plan = compute_session_plan(
        nodes,
        read_registry(registry_path(root)),
        unauthored=unauthored_leaves(root, nodes),
    )
    lines = ["Waves (a leaf starts once its own dependencies are Complete):"]
    lines += [f"  wave {w.index}: {', '.join(w.node_ids)}" for w in plan.waves]
    lines.append(f"Ready now: {', '.join(plan.ready) or '—'}")
    lines += [f"Blocked: {b.node_id} waiting on {', '.join(b.waiting_on)}" for b in plan.blocked]
    lines += [f"Unauthored: {u.node_id} ({u.reason})" for u in plan.unauthored]
    return lines


def cmd_apply(args: object) -> None:
    root = repo_root(args)
    path = Path(args.changes_file)
    try:
        changes = parse_change_file(path)
        if args.dry_run:
            before = load_roadmap(root)["nodes"]
            with _scratch_root(root) as scratch:
                log = _run_changes(changes, scratch)
                preview = id_map_lines(before, load_roadmap(scratch)["nodes"])
                preview += wave_preview(scratch)
        else:
            log = _apply_in_place(changes, root)
            preview = wave_preview(root)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        raise SystemExit(1) from None
    if args.dry_run:
        print(f"dry run: rehearsed {len(changes)} change(s) on a scratch copy")
    print(log, end="")
    print("\n".join(preview))
    if args.dry_run:
        print(f"[ok] {path} validates; nothing was written (re-run without --dry-run to apply)")
    else:
        print(f"[ok] applied {len(changes)} change(s) from {path}")
