"""Decide *what* an archive would move, without touching disk.

Split from :mod:`specy_road.archive_ops` so ``--dry-run`` and the PM GUI's
eligibility check can reuse the exact reasoning the real archive runs, instead
of a second approximation of it that can drift.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from specy_road.registry_yaml import read_registry, registry_path
from specy_road.archive_index import find_record, load_archive_index, node_summary
from specy_road.milestone_subtree import subtree_node_ids
from specy_road.runtime_paths import bundled_scripts_dir


@dataclass(frozen=True)
class ChunkEdit:
    """One source chunk: what is left in it, and where the removed nodes sat.

    ``taken`` keeps each archived node's original array index so restore can put
    it back in the same slot instead of appending, which would otherwise churn
    the chunk diff every time an archive round-trips.
    """

    path: Path
    rel: str
    remaining: tuple[dict[str, Any], ...]
    taken: tuple[tuple[int, dict[str, Any]], ...]

    @property
    def emptied(self) -> bool:
        return not self.remaining


@dataclass(frozen=True)
class ArchivePlan:
    archive_id: str
    root_node_id: str
    root_node_key: str
    nodes: tuple[dict[str, Any], ...]
    chunk_edits: tuple[ChunkEdit, ...]
    planning_paths: tuple[str, ...]
    archived_at: str
    git: dict[str, Any] = field(default_factory=dict)

    @property
    def node_keys(self) -> list[str]:
        return [n["node_key"] for n in self.nodes if isinstance(n.get("node_key"), str)]

    @property
    def node_ids(self) -> list[str]:
        return [n["id"] for n in self.nodes if isinstance(n.get("id"), str)]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def build_archive_id(node: dict[str, Any], archived_at: str) -> str:
    """``<node_id>-<node_key[:8]>-<YYYYMMDD>`` — stable, readable, path-safe."""
    nid = str(node.get("id") or "node")
    key = str(node.get("node_key") or "")[:8] or "nokey"
    day = archived_at[:10].replace("-", "")
    safe = "".join(c for c in nid if c.isalnum() or c in "._-") or "node"
    return f"{safe}-{key}-{day}"


def unique_archive_id(root: Path, base_id: str) -> str:
    """Append ``-2``, ``-3``… when the same subtree is archived twice in a day."""
    doc = load_archive_index(root)
    if find_record(doc, base_id) is None:
        return base_id
    n = 2
    while find_record(doc, f"{base_id}-{n}") is not None:
        n += 1
    return f"{base_id}-{n}"


def assert_archivable(
    nodes: list[dict[str, Any]], node_id: str, *, force: bool = False
) -> dict[str, Any]:
    """Return the root node, or raise ``ValueError`` explaining why it can't archive."""
    from specy_road.bundled_scripts.roadmap_load import compute_rollup_status

    from specy_road.milestone_lock import assert_pm_nodes_not_milestone_locked

    by_id = {n["id"]: n for n in nodes if isinstance(n.get("id"), str)}
    node = by_id.get(node_id)
    if node is None:
        raise ValueError(f"no roadmap node with id {node_id!r} (not found in any chunk)")

    # An active milestone rollup owns its whole subtree; moving files out from
    # under it would strand the in-flight branch. --force does not override this.
    #
    # Check every node being archived, not just the root: the lock marks the
    # locked milestone and its DESCENDANTS, so archiving an ANCESTOR of a
    # locked milestone would pass a root-only check while carrying the locked
    # subtree out with it.
    assert_pm_nodes_not_milestone_locked(nodes, *subtree_node_ids(node_id, nodes))

    if not force:
        rollup = compute_rollup_status(nodes).get(node_id)
        if rollup != "Complete":
            raise ValueError(
                f"node {node_id} rolls up as {rollup!r}, not 'Complete' — archiving "
                "it would move unfinished work out of the live roadmap. Finish the "
                "subtree first, or pass --force if you really mean to."
            )
    return node


def _split_chunk(
    nodes_in_chunk: list[dict[str, Any]], subtree_ids: set[str]
) -> tuple[list[tuple[int, dict[str, Any]]], list[dict[str, Any]]]:
    """Partition a chunk into ``([(original_index, node)], remaining)``."""
    taken = [
        (i, n) for i, n in enumerate(nodes_in_chunk) if n.get("id") in subtree_ids
    ]
    left = [n for n in nodes_in_chunk if n.get("id") not in subtree_ids]
    return taken, left


def plan_archive(
    root: Path,
    node_id: str,
    *,
    force: bool = False,
    archived_at: str | None = None,
) -> ArchivePlan:
    """Work out every file move an archive of ``node_id`` implies.

    Handles the awkward shapes directly: a subtree spread across several chunks,
    and a subtree sharing a chunk with live nodes. Both are resolved the same
    way — pull the subtree's nodes into one archive chunk and rewrite whatever
    remains back to each source.
    """
    from specy_road.bundled_scripts.roadmap_chunk_utils import (
        build_node_chunk_map,
        load_json_chunk,
        roadmap_dir,
    )
    from specy_road.bundled_scripts.roadmap_load import load_roadmap

    from specy_road.archive_git import capture_provenance

    nodes = load_roadmap(root)["nodes"]
    root_node = assert_archivable(nodes, node_id, force=force)
    subtree_ids = subtree_node_ids(node_id, nodes)

    chunk_map = build_node_chunk_map(root)
    base = roadmap_dir(root)
    touched: dict[Path, None] = {}
    for nid in subtree_ids:
        p = chunk_map.get(nid)
        if p is not None:
            touched[p] = None

    archived_nodes: list[dict[str, Any]] = []
    edits: list[ChunkEdit] = []
    for path in touched:
        taken, left = _split_chunk(load_json_chunk(path), subtree_ids)
        archived_nodes.extend(n for _, n in taken)
        try:
            rel = path.resolve().relative_to(base).as_posix()
        except ValueError:
            rel = path.name
        edits.append(
            ChunkEdit(
                path=path, rel=rel, remaining=tuple(left), taken=tuple(taken)
            )
        )

    if not archived_nodes:
        raise ValueError(
            f"node {node_id} resolved to no chunk nodes — nothing to archive"
        )

    _refuse_if_manifest_would_empty(root, edits)
    _refuse_if_claimed(root, subtree_ids)

    archived_nodes.sort(key=lambda n: _id_sort_key(str(n.get("id") or "")))
    when = archived_at or utc_now_iso()

    return ArchivePlan(
        archive_id=unique_archive_id(root, build_archive_id(root_node, when)),
        root_node_id=node_id,
        root_node_key=str(root_node.get("node_key") or ""),
        nodes=tuple(archived_nodes),
        chunk_edits=tuple(edits),
        planning_paths=tuple(_planning_paths(archived_nodes)),
        archived_at=when,
        git=capture_provenance(root, root_node),
    )


def _refuse_if_claimed(root: Path, subtree_ids: set[str]) -> None:
    """Refuse to archive a node someone still has an open registry claim on.

    ``validate`` rejects a registry entry whose ``node_id`` is not in the merged
    graph, so archiving a claimed node leaves the repository failing validation
    with no hint about why — and strands the claimant's feature branch. Caught
    at plan time so nothing has moved yet.
    """

    try:
        entries = read_registry(registry_path(root)).get("entries") or []
    except Exception:  # noqa: BLE001 - a registry problem is validate's to report
        return
    claimed = [
        e for e in entries
        if isinstance(e, dict) and e.get("node_id") in subtree_ids
    ]
    if not claimed:
        return
    detail = ", ".join(
        f"{e.get('node_id')} ({e.get('branch') or e.get('codename')})"
        for e in claimed
    )
    raise ValueError(
        f"in-progress work is still registered on this subtree: {detail}. "
        "Finish it (specy-road finish-this-task) or release the claim "
        "(specy-road abort-task-pickup) before archiving."
    )


def _refuse_if_manifest_would_empty(root: Path, edits: list[ChunkEdit]) -> None:
    """Never leave ``manifest.json`` with an empty ``includes``.

    This used to be load-bearing against a crash: the chunk-map helpers read a
    falsy ``includes`` as the legacy "nodes live in the manifest" layout and
    tried to parse ``manifest.json`` as a chunk. They now agree with the loader
    that empty means no chunks, so the guard stands on its own terms -- a
    roadmap with nothing live in it is not a state to archive a repo into.
    """
    from specy_road.bundled_scripts.roadmap_chunk_utils import load_manifest_mapping

    includes = [
        rel for rel in (load_manifest_mapping(root).get("includes") or [])
        if isinstance(rel, str)
    ]
    emptied = {e.rel for e in edits if e.emptied}
    if includes and not [rel for rel in includes if rel not in emptied]:
        raise ValueError(
            "archiving this subtree would empty the roadmap: every remaining "
            "chunk in manifest.json would be removed, leaving a repository "
            "that cannot load. Keep at least one live node."
        )


def _id_sort_key(node_id: str) -> tuple:
    """Natural order for ``M1.10`` vs ``M1.2`` so archived chunks read sensibly."""
    parts = node_id.lstrip("Mm").split(".")
    out: list[tuple[int, object]] = []
    for p in parts:
        out.append((0, int(p)) if p.isdigit() else (1, p))
    return tuple(out)


def _planning_paths(nodes: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for n in nodes:
        pd = n.get("planning_dir")
        if isinstance(pd, str) and pd.strip():
            out.append(pd.strip())
    return out


def plan_summary(plan: ArchivePlan) -> list[str]:
    """Operator-facing dry-run lines."""
    lines = [
        f"archive_id      {plan.archive_id}",
        f"root            {plan.root_node_id} ({plan.root_node_key[:8]})",
        f"nodes           {len(plan.nodes)}: {', '.join(plan.node_ids)}",
    ]
    for e in plan.chunk_edits:
        what = (
            "emptied — removed from manifest"
            if e.emptied
            else f"{len(e.remaining)} node(s) left"
        )
        lines.append(f"chunk           {e.rel} -> {what}")
    for move in planning_moves(plan):
        lines.append(f"planning        {move['origin']} -> {move['stored']}")
    git = plan.git or {}
    if git.get("merge_commit") or git.get("nearest_tag"):
        lines.append(
            f"git             merge={str(git.get('merge_commit') or '-')[:12]} "
            f"tag={git.get('nearest_tag') or '-'}"
        )
    return lines


def planning_moves(plan: ArchivePlan) -> list[dict[str, str]]:
    """``{origin, stored}`` per planning sheet, filename preserved.

    ``stored`` lands under ``roadmap/archive/planning/<archive_id>/`` — see
    :func:`specy_road.archive_index.archive_planning_dir` for why not
    ``planning/archive/``.
    """
    out: list[dict[str, str]] = []
    for origin in plan.planning_paths:
        name = Path(origin).name
        out.append(
            {
                "origin": origin,
                "stored": f"roadmap/archive/planning/{plan.archive_id}/{name}",
            }
        )
    return out


def source_entries(plan: ArchivePlan) -> list[dict[str, Any]]:
    """``{chunk, node_key, index}`` per archived node — restore replays these."""
    out: list[dict[str, Any]] = []
    for edit in plan.chunk_edits:
        for idx, node in edit.taken:
            key = node.get("node_key")
            if isinstance(key, str):
                out.append({"chunk": edit.rel, "node_key": key, "index": idx})
    return out


def build_record(plan: ArchivePlan, *, chunk_rel: str) -> dict[str, Any]:
    """The ``archive/index.json`` record for a freshly-applied shallow archive."""
    return {
        "archive_id": plan.archive_id,
        "depth": "shallow",
        "root_node_id": plan.root_node_id,
        "root_node_key": plan.root_node_key,
        "archived_at": plan.archived_at,
        "node_keys": plan.node_keys,
        "nodes_summary": [node_summary(n) for n in plan.nodes],
        "chunk": chunk_rel,
        "sources": source_entries(plan),
        "planning": planning_moves(plan),
        "bundle": None,
        "git": plan.git or None,
    }
