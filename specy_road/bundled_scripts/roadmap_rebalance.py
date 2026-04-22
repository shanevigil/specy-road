#!/usr/bin/env python3
"""Power-user maintenance: re-pack roadmap chunks into balanced JSON files.

Normal authoring never needs this command — :mod:`roadmap_chunk_router`
auto-routes new nodes into the right chunk on every write. Use
``specy-road rebalance-chunks`` after a heavy manual edit, after
restoring an old branch, or to consolidate fragmented part-files into
one chunk per phase.

Algorithm (deterministic):

1. Load merged nodes (already in outline order).
2. Group nodes by their phase ancestor (or "no phase" bucket).
3. For each group, in tree order, first-fit pack into chunks of
   ``<= roadmap_json_chunk_max_lines``.
4. The first chunk per phase keeps the existing primary chunk path;
   overflow chunks use ``<phase_stem>__<6hex-of-first-node-key>.json``.
5. Build the new ``manifest.json`` ``includes`` list in tree order.
6. Apply via :class:`AtomicWritePlan` so failure rolls back to the
   pre-call state.

Idempotent: running on an already-balanced repo is a no-op.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from roadmap_chunk_atomic import AtomicWritePlan
from roadmap_chunk_router import _validate_callback  # noqa: PLC2701 (deliberate re-use)
from roadmap_chunk_router_pick import (
    chunk_max_lines,
    load_merged_nodes,
    phase_ancestor_id,
    simulate_chunk_lines,
    strip_partN_suffix,
)
from roadmap_chunk_utils import (
    build_node_chunk_map,
    load_manifest_mapping,
    render_json_chunk,
    roadmap_dir,
)
from roadmap_layout import ordered_tree_rows
from specy_road.runtime_paths import default_user_repo_root


@dataclass
class _PackPlan:
    chunk_writes: dict[Path, list[dict]]
    deletes: set[Path]
    new_includes: list[str]


def _phase_id_for_node(merged: list[dict], node: dict) -> str | None:
    """Phase ancestor for this node (the node's own id if it is a phase)."""
    if node.get("type") == "phase":
        nid = node.get("id")
        return nid if isinstance(nid, str) else None
    pid = node.get("parent_id")
    if not isinstance(pid, str):
        return None
    return phase_ancestor_id(merged, pid)


def _group_by_phase(
    merged: list[dict],
) -> list[tuple[str | None, list[dict]]]:
    """Return ``[(phase_id_or_None, [nodes_in_tree_order])]`` (preserves outline order)."""
    rows = [n for n, _depth in ordered_tree_rows(merged)]
    buckets: dict[str | None, list[dict]] = {}
    order: list[str | None] = []
    for n in rows:
        ph = _phase_id_for_node(merged, n)
        if ph not in buckets:
            buckets[ph] = []
            order.append(ph)
        buckets[ph].append(n)
    return [(ph, buckets[ph]) for ph in order]


def _phase_primary_chunk_rel(
    root: Path, phase_id: str | None, group: list[dict]
) -> str:
    """Return a stable relative chunk path for this phase's first chunk.

    For phase-rooted groups, prefer the chunk that currently holds any node
    from the group (deterministic: pick the path that sorts first when the
    group has multiple chunks). For unparented "orphan" nodes (no phase
    ancestor), use a dedicated ``phases/orphans.json`` so they don't collide
    with phase chunks.
    """
    chunk_map = build_node_chunk_map(root)
    base = roadmap_dir(root)
    held: set[str] = set()
    for n in group:
        nid = n.get("id")
        if not isinstance(nid, str):
            continue
        chunk = chunk_map.get(nid)
        if chunk:
            held.add(chunk.relative_to(base).as_posix())
    if held:
        # Prefer the path that does NOT carry the ``__<hex>`` overflow suffix,
        # then sort lexicographically for determinism.
        primary = sorted(
            held,
            key=lambda p: (1 if "__" in Path(p).stem else 0, p),
        )[0]
        return primary
    if phase_id:
        return f"phases/{phase_id}.json"
    return "phases/orphans.json"


def _pack_group(
    primary_rel: str,
    group: list[dict],
    max_lines: int,
) -> tuple[list[tuple[str, list[dict]]], list[str]]:
    """First-fit pack ``group`` into chunks. Returns ``[(rel_path, nodes), ...]`` + manifest order."""
    chunks: list[tuple[str, list[dict]]] = []
    current: list[dict] = []
    current_rel = primary_rel
    for node in group:
        candidate = [*current, node]
        lines = simulate_chunk_lines(candidate)
        if not current or lines <= max_lines:
            current = candidate
        else:
            # Persist current and start a fresh chunk seeded by ``node``.
            chunks.append((current_rel, current))
            current = [node]
            # Deterministic overflow filename seeded by the new chunk's first node,
            # so the same input always produces the same chunk filenames.
            current_rel = _stable_overflow_path(primary_rel, node)
    if current:
        chunks.append((current_rel, current))
    manifest_order = [rel for rel, _ in chunks]
    return chunks, manifest_order


def _stable_overflow_path(primary_rel: str, seed_node: dict) -> str:
    """Deterministic overflow chunk path seeded by the first node placed in it."""
    p = Path(primary_rel)
    parent = p.parent.as_posix()
    stem = strip_partN_suffix(p.stem)
    nk_hex = "".join(
        c for c in (str(seed_node.get("node_key") or "")).lower()
        if c in "0123456789abcdef"
    )
    suffix = nk_hex[:6] or "x" * 6
    fname = f"{stem}__{suffix}.json"
    return f"{parent}/{fname}" if parent and parent != "." else fname


def build_pack_plan(root: Path) -> _PackPlan:
    """Compute the rebalanced manifest + chunk writes (no disk IO)."""
    base = roadmap_dir(root)
    max_lines = chunk_max_lines(root)
    merged = load_merged_nodes(root)
    groups = _group_by_phase(merged)

    chunk_writes: dict[Path, list[dict]] = {}
    new_includes: list[str] = []

    for phase_id, group in groups:
        primary_rel = _phase_primary_chunk_rel(root, phase_id, group)
        # If a previous group already claimed this chunk path, derive an
        # overflow filename for this group so we don't clobber writes.
        primary_abs = (base / primary_rel).resolve()
        if primary_abs in chunk_writes:
            primary_rel = _stable_overflow_path(primary_rel, group[0])
        chunks, manifest_order = _pack_group(primary_rel, group, max_lines)
        for rel, nodes in chunks:
            abs_path = (base / rel).resolve()
            try:
                abs_path.relative_to(base)
            except ValueError as e:
                raise ValueError(
                    f"computed chunk path escapes roadmap/: {rel!r}"
                ) from e
            chunk_writes[abs_path] = nodes
        new_includes.extend(manifest_order)

    # Deletes: any existing chunk that the new plan does not write.
    existing_chunks: set[Path] = set()
    for rel in (load_manifest_mapping(root).get("includes") or []):
        if not isinstance(rel, str):
            continue
        existing_chunks.add((base / rel).resolve())
    deletes = {p for p in existing_chunks if p not in chunk_writes}

    return _PackPlan(
        chunk_writes=chunk_writes,
        deletes=deletes,
        new_includes=new_includes,
    )


def _diff_summary(plan: _PackPlan, root: Path) -> str:
    base = roadmap_dir(root)
    out: list[str] = []
    for path, nodes in sorted(plan.chunk_writes.items(), key=lambda t: str(t[0])):
        rel = path.relative_to(base).as_posix()
        if not path.is_file():
            out.append(f"  + roadmap/{rel}  ({len(nodes)} nodes)")
        else:
            current = path.read_text(encoding="utf-8")
            new_text = render_json_chunk(nodes)
            if current == new_text:
                out.append(f"    roadmap/{rel}  ({len(nodes)} nodes, unchanged)")
            else:
                out.append(f"  ~ roadmap/{rel}  ({len(nodes)} nodes)")
    for path in sorted(plan.deletes, key=str):
        rel = path.relative_to(base).as_posix()
        out.append(f"  - roadmap/{rel}")
    out.append(f"  manifest includes: {len(plan.new_includes)} entries")
    return "\n".join(out)


def apply_pack_plan(root: Path, plan: _PackPlan) -> None:
    """Apply ``plan`` atomically and validate; restore on failure."""
    write_plan = AtomicWritePlan(root=root)
    for path, nodes in plan.chunk_writes.items():
        write_plan.stage_chunk(path, nodes)
    manifest_doc = load_manifest_mapping(root)
    manifest_doc["includes"] = list(plan.new_includes)
    write_plan.stage_manifest(manifest_doc)
    # Independently snapshot files we are about to delete so we can restore.
    delete_snapshots: dict[Path, bytes] = {}
    for path in plan.deletes:
        if path.is_file():
            delete_snapshots[path] = path.read_bytes()
    write_plan.write()
    for path in plan.deletes:
        if path.is_file():
            try:
                path.unlink()
            except OSError:
                pass
    try:
        _validate_callback(root)()
    except BaseException:
        for path, original in delete_snapshots.items():
            if not path.is_file():
                try:
                    path.write_bytes(original)
                except OSError:
                    pass
        write_plan.rollback()
        raise


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        metavar="DIR",
        help="Repository root (default: git root or cwd).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the rebalance summary without writing.",
    )
    args = parser.parse_args(argv)
    root = (args.repo_root or default_user_repo_root()).resolve()
    plan = build_pack_plan(root)
    summary = _diff_summary(plan, root)
    print("rebalance-chunks plan:")
    print(summary or "  (no changes)")
    if args.dry_run:
        print("\n(dry-run; no files written)")
        return
    if not plan.chunk_writes and not plan.deletes:
        print("\n(repo is already balanced; nothing to do)")
        return
    apply_pack_plan(root, plan)
    print("\nrebalance-chunks: applied; specy-road validate passed.")


if __name__ == "__main__":
    main()
