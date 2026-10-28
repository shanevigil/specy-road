"""Roadmap dependency CRUD for the CLI (same edit path as the PM GUI patch).

Also ``apply``: a file of ``add-node`` / ``edit-node`` / ``add-dependency``
changes run as one batch. It lives here because a batch is mostly dependency
wiring between nodes it creates, which is why dependencies accept display ids.
"""

from __future__ import annotations

import contextlib
import io
import shutil
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path

import yaml

from specy_road.bundled_scripts.roadmap_chunk_utils import find_chunk_path
from specy_road.bundled_scripts.roadmap_crud_ops import edit_node_set_pairs, repo_root, unknown_node_msg
from specy_road.bundled_scripts.planning_artifacts import normalize_planning_dir
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


# ---------------------------------------------------------------------------
# apply: a change file as one batch
# ---------------------------------------------------------------------------

APPLY_OPS = ("add-node", "edit-node", "add-dependency")
# Node field names read naturally in a change file; the CLI flags are singular.
_OPTION_ALIASES = {"dependencies": "dependency", "touch_zones": "touch-zone"}


def _option_argv(key: str, value: object) -> list[str]:
    flag = "--" + _OPTION_ALIASES.get(key, key).replace("_", "-")
    if isinstance(value, bool):
        return [flag] if value else []
    if value is None:
        # ``parent_id: null`` is a phase root; any other null leaves the option unset.
        return [flag, "null"] if flag == "--parent-id" else []
    items = value if isinstance(value, list) else [value]
    return [part for item in items for part in (flag, str(item))]


def _entry_argv(entry: object) -> list[str]:
    """The command line one change-file entry stands for."""
    if not isinstance(entry, dict) or entry.get("op") not in APPLY_OPS:
        raise ValueError(f"each change needs op: one of {', '.join(APPLY_OPS)}")
    rest = {k: v for k, v in entry.items() if k != "op"}
    argv = [entry["op"]]
    if argv[0] != "add-node":
        positional = ["node"] + (["dependency"] if argv[0] == "add-dependency" else [])
        for key in positional:
            if rest.get(key) in (None, ""):
                raise ValueError(f"{argv[0]} needs {key}:")
            argv.append(str(rest.pop(key)))
    if argv[0] == "edit-node":
        sets = rest.pop("set", None)
        if not isinstance(sets, dict) or not sets:
            raise ValueError("edit-node needs set: a mapping of field: value")
        for k, v in sets.items():
            for item in v if isinstance(v, list) else [v]:
                argv += ["--set", f"{k}={'' if item is None else item}"]
    for k, v in rest.items():
        argv += _option_argv(k, v)
    return argv


def parse_change_file(root: Path, path: Path) -> list[object]:
    """Parse every entry before anything runs, so a malformed one changes nothing.

    Each entry goes through the real subcommand parser: an option the command
    does not take, a bad ``type``, a missing ``title`` are refused here.
    """
    from specy_road.bundled_scripts.roadmap_crud_argparse import build_parser

    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as e:
        raise ValueError(f"cannot read {path}: {e}") from None
    entries = doc.get("changes") if isinstance(doc, dict) else doc
    if not isinstance(entries, list) or not entries:
        raise ValueError(f"{path}: expected a list of changes (or changes: [...])")
    parser = build_parser()
    out: list[object] = []
    for i, entry in enumerate(entries, 1):
        try:
            argv = _entry_argv(entry)
            out.append(parser.parse_args(["--repo-root", str(root), *argv]))
        except ValueError as e:
            raise ValueError(f"change {i}: {e}") from None
        except SystemExit:
            raise ValueError(f"change {i}: not a valid {argv[0]} (usage above)") from None
    return out


def _run_changes(changes: list[object], root: Path) -> str:
    """Run each change's command in order; the first refusal stops the batch.

    Returns the commands' ``[ok]`` lines, held back until every change has run:
    printed as they happened, a refused batch would still list ``[ok]`` for
    changes it then rolled back. Errors go to stderr and are not held.
    """
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        for i, ns in enumerate(changes, 1):
            ns.repo_root = root
            try:
                ns.func(ns)
            except SystemExit as e:
                if e.code not in (0, None):
                    raise ValueError(
                        f"change {i} ({ns.cmd}) failed; no change in the batch was applied"
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


def _files_under(paths: list[Path]) -> list[Path]:
    out: list[Path] = []
    for p in paths:
        if p.is_file():
            out.append(p)
        elif p.is_dir():
            out.extend(f for f in p.rglob("*") if f.is_file())
    return out


def _restore(paths: list[Path], before: dict[Path, bytes]) -> None:
    """Put ``paths`` back byte-for-byte: drop new files, rewrite changed ones."""
    for f in _files_under(paths):
        if f not in before:
            f.unlink()
    for f, data in before.items():
        if not f.is_file() or f.read_bytes() != data:
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(data)


def _apply_in_place(changes: list[object], root: Path) -> str:
    """Run the batch all or nothing.

    Each command commits its own transaction, so the batch holds a snapshot of
    everything they can write and restores it if any one refuses.
    """
    paths = _graph_paths(root)
    before = {f: f.read_bytes() for f in _files_under(paths)}
    try:
        return _run_changes(changes, root)
    except BaseException:
        _restore(paths, before)
        raise


@contextlib.contextmanager
def _scratch_root(root: Path) -> Iterator[Path]:
    """A throwaway root to rehearse in: graph files copied, the rest linked.

    The rehearsal runs the same commands as a real apply, so it needs somewhere
    to write. Schemas, constraints and the source tree (touch-zone checks read
    it) are symlinked; ``.git`` is left out so nothing can reach the real index.
    """
    copied = {p.name for p in _graph_paths(root)}
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
        changes = parse_change_file(root, path)
        if args.dry_run:
            with _scratch_root(root) as scratch:
                log = _run_changes(changes, scratch)
                preview = wave_preview(scratch)
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
