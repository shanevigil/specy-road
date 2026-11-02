"""Chunk write provenance for ``add-node`` / ``edit-node`` CLI output (M11.17)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


def repo_rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


@dataclass(frozen=True)
class NodeChunkWriteReport:
    node_id: str
    read_from: str | None
    written: tuple[str, ...]
    relocated: bool = False
    moved_from: str | None = None
    moved_to: str | None = None


def _unique_commit_paths(*groups: list[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    out: list[str] = []
    for group in groups:
        for rel in group:
            if rel not in seen:
                seen.add(rel)
                out.append(rel)
    return tuple(out)


def _manifest_rel(root: Path) -> str:
    from specy_road.bundled_scripts.roadmap_chunk_utils import discover_manifest_path

    return repo_rel(root, discover_manifest_path(root))


def plan_edit_chunk_writes(
    root: Path,
    node_id: str,
    source_chunk: Path,
    nodes_after: list[dict],
    renames: list[tuple[Path, Path]] | None,
) -> NodeChunkWriteReport:
    from specy_road.bundled_scripts.roadmap_chunk_router import chunk_max_lines
    from specy_road.bundled_scripts.roadmap_chunk_router_pick import (
        pick_target_chunk,
        simulate_chunk_lines,
    )

    read_from = repo_rel(root, source_chunk)
    max_lines = chunk_max_lines(root)
    written: list[str] = []
    relocated = False
    moved_from: str | None = None
    moved_to: str | None = None

    if len(nodes_after) >= 2 and simulate_chunk_lines(nodes_after) > max_lines:
        target = next(
            (n for n in nodes_after if isinstance(n, dict) and n.get("id") == node_id),
            None,
        )
        if target is not None:
            pid_raw = target.get("parent_id")
            parent_id = pid_raw if isinstance(pid_raw, str) else None
            decision = pick_target_chunk(
                root,
                parent_id,
                hint_chunk_rel=None,
                new_node=target,
                max_lines=max_lines,
            )
            if decision.chunk_path != source_chunk or decision.is_new_chunk:
                relocated = True
                moved_from = read_from
                moved_to = repo_rel(root, decision.chunk_path)
                written.extend((moved_from, moved_to))
                if decision.is_new_chunk:
                    written.append(_manifest_rel(root))
    if not relocated:
        written.append(read_from)

    for _src, dst in renames or []:
        written.append(repo_rel(root, dst))

    return NodeChunkWriteReport(
        node_id=node_id,
        read_from=read_from,
        written=_unique_commit_paths(written),
        relocated=relocated,
        moved_from=moved_from,
        moved_to=moved_to,
    )


def plan_add_chunk_writes(
    root: Path,
    parent_id: str | None,
    chunk_arg: str | None,
    node: dict,
    *,
    planned_sheet: tuple[Path, str] | None,
) -> NodeChunkWriteReport:
    from specy_road.bundled_scripts.roadmap_chunk_router_pick import pick_target_chunk

    decision = pick_target_chunk(root, parent_id, chunk_arg, node)
    written = [repo_rel(root, decision.chunk_path)]
    if planned_sheet:
        written.append(repo_rel(root, planned_sheet[0]))
    if decision.is_new_chunk:
        written.append(_manifest_rel(root))
    return NodeChunkWriteReport(
        node_id=str(node.get("id") or ""),
        read_from=None,
        written=_unique_commit_paths(written),
    )


def print_node_chunk_write_report(report: NodeChunkWriteReport, *, verb: str) -> None:
    parts = [f"[ok] {verb} {report.node_id}"]
    if report.read_from:
        parts.append(f"read from {report.read_from}")
    if report.relocated and report.moved_from and report.moved_to:
        parts.append(f"moved from {report.moved_from} to {report.moved_to}")
    elif report.written:
        parts.append(f"wrote {', '.join(report.written)}")
    print(" ".join(parts))
    print(f"commit these files: {', '.join(report.written)}")
