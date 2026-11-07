"""Stage the chunk, planning-sheet and registry rewrites a display-id change implies.

Moved out of ``roadmap_move_node`` (file-limits cap) unchanged; used by its
``stage_id_rewrite``, which both ``move_node`` and the PM GUI's
``reorder_siblings`` commit through one :class:`AtomicWritePlan`.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from specy_road.bundled_scripts.planning_artifacts import resolve_planning_path
from specy_road.bundled_scripts.planning_rename import stage_prose_refs
from specy_road.bundled_scripts.roadmap_chunk_atomic import AtomicWritePlan
from specy_road.bundled_scripts.roadmap_chunk_utils import (
    load_json_chunk,
    manifest_includes,
    roadmap_dir,
)
from specy_road.registry_yaml import registry_path
from specy_road.runtime_paths import project_prefix


def _stage_merged_nodes(plan: AtomicWritePlan, root: Path, merged: list[dict]) -> None:
    """Stage every chunk rewritten by the move (match by ``node_key``, preserve chunk order)."""
    by_key = {n["node_key"]: n for n in merged}
    base = roadmap_dir(root)
    for rel in manifest_includes(root):
        path = (base / rel).resolve()
        if not path.is_file() or path.suffix.lower() != ".json":
            continue
        out = []
        for old in load_json_chunk(path):
            key = old.get("node_key")
            if not isinstance(key, str) or key not in by_key:
                raise ValueError(f"chunk {rel}: unknown node_key {key!r}")
            out.append(by_key[key])
        plan.stage_chunk(path, out)


def _stage_planning_moves(
    plan: AtomicWritePlan,
    root: Path,
    moves: list[tuple[str, str, str]],
    nodes: list[dict] | None = None,
    prose_map: dict[str, str] | None = None,
) -> None:
    """Stage the sheet renames a renumber implies.

    Every source is read before anything is staged for deletion, because a
    renumber routinely produces chains (``M1.3`` -> ``M1.2`` -> ``M1.1``) and a
    naive rename-at-a-time would consume a file another move still needs.

    Given ``prose_map`` (``--rewrite-refs``), it then rewrites those ids in
    every one of ``nodes``' sheets (over the staged renames), titles and
    acceptance; call it before the chunks are staged, since it edits ``nodes``.
    """
    payloads: dict[Path, str] = {}
    sources: list[Path] = []
    for _nk, old_rel, new_rel in moves:
        src = resolve_planning_path(root, old_rel)
        if not src.is_file():
            continue
        payloads[resolve_planning_path(root, new_rel)] = src.read_text(
            encoding="utf-8"
        )
        sources.append(src)
    for dst, text in payloads.items():
        plan.stage_text(dst, text)
    for src in sources:
        if src not in payloads:
            plan.stage_delete(src)
    if prose_map is not None and nodes is not None:
        stage_prose_refs(plan, root, nodes, prose_map)


def sheet_path_map(root: Path, moves: list[tuple[str, str, str]]) -> dict[str, str]:
    """Old -> new sheet path for each sheet move, in project and checkout form.

    A zone may name a sheet relative to the project root (``planning/<file>``)
    or to the git root (``sr/planning/<file>`` for a project at ``sr/``).
    """
    prefix = project_prefix(root)
    out: dict[str, str] = {}
    for _nk, old_rel, new_rel in moves:
        out[old_rel] = new_rel
        if prefix:
            out[prefix + old_rel] = prefix + new_rel
    return out


def _rewrite_zone(zone: str, renamed: dict[str, str], sheets: dict[str, str]) -> str:
    if zone in sheets:
        return sheets[zone]
    return "/".join(renamed.get(seg, seg) for seg in zone.split("/"))


def _rewrite_touch_zones(
    items: list, renamed: dict[str, str], sheets: dict[str, str] | None = None
) -> bool:
    """Replace every touch-zone path segment equal to a renumbered display id.

    A zone such as ``docs/M1.2/`` names the node by position, so a renumber
    would leave it pointing at whatever now sits at ``M1.2``. Only whole
    segments match: ``M1.2`` in ``docs/M1.2.1/`` or ``M1.2-notes`` is left
    alone. Each segment is looked up once in the old -> new map, so chains
    (``M1.3`` -> ``M1.2`` -> ``M1.1``) resolve to the node the zone named.
    A whole zone equal to a key of ``sheets`` (a renamed planning sheet, see
    :func:`sheet_path_map`) becomes that sheet's new path instead.
    Returns whether anything changed.
    """
    sheets = sheets or {}
    changed = False
    for item in items:
        zones = item.get("touch_zones") if isinstance(item, dict) else None
        if not isinstance(zones, list):
            continue
        new = [
            _rewrite_zone(z, renamed, sheets) if isinstance(z, str) else z
            for z in zones
        ]
        if new != zones:
            item["touch_zones"] = new
            changed = True
    return changed


def _stage_registry_ids(
    plan: AtomicWritePlan,
    root: Path,
    renamed: dict[str, str],
    sheets: dict[str, str],
    *,
    claims_in_map_only: bool,
) -> None:
    """Stage the registry rewrite so claims still point at the moved nodes.

    A claim carries its own copy of the node's touch zones, which the finish
    check reads first, so those segments, and zones naming a renamed sheet
    (``sheets``), are rewritten too. With
    ``claims_in_map_only`` (a subtree move) only claims whose ``node_id`` is a
    renamed id are touched at all; another claim keeps its zones even when one
    names a moved id.
    """
    path = registry_path(root)
    if not (renamed or sheets) or not path.is_file():
        return
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("entries"), list):
        return
    entries = [
        e
        for e in data["entries"]
        if not claims_in_map_only
        or (isinstance(e, dict) and e.get("node_id") in renamed)
    ]
    changed = _rewrite_touch_zones(entries, renamed, sheets)
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        nid = entry.get("node_id")
        if isinstance(nid, str) and nid in renamed:
            entry["node_id"] = renamed[nid]
            changed = True
    if changed:
        plan.stage_text(
            path,
            yaml.dump(
                data, default_flow_style=False, allow_unicode=True, sort_keys=False
            ),
        )
