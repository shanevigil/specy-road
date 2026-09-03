"""PM Gantt API routes for archiving completed subtrees.

Read routes list what is archived and what is eligible; write routes archive,
deepen and restore. Every write goes through ``require_pm_gui_write_header``
like the rest of the mutating API — an archive moves roadmap files, so a stale
browser tab must not be able to fire one against a graph it has not seen.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from specy_road.archive_deep import deepen_archive
from specy_road.archive_index import find_record, index_records, load_archive_index
from specy_road.archive_ops import archive_node, auto_archive_candidates
from specy_road.archive_plan import plan_archive, plan_summary
from specy_road.archive_restore import restore_archive
from specy_road.gui_app_helpers import get_repo_root
from specy_road.pm_gui_concurrency import require_pm_gui_write_header

def _reexport_roadmap_md(root: Path) -> None:
    """Keep ``roadmap.md`` in step so the repo does not drift into a failing CI."""

    from specy_road.bundled_scripts.export_roadmap_md import reexport_roadmap_md

    reexport_roadmap_md(root)


DEFAULT_AUTO_DAYS = 90


class ArchiveCreateBody(BaseModel):
    node_id: str
    deep: bool = False
    force: bool = False


class ArchiveAutoBody(BaseModel):
    older_than_days: int = DEFAULT_AUTO_DAYS
    dry_run: bool = False


def _record_or_404(root: Path, archive_id: str) -> dict[str, Any]:
    rec = find_record(load_archive_index(root), archive_id)
    if rec is None:
        raise HTTPException(status_code=404, detail=f"no archive {archive_id!r}")
    return rec


def _eligible(root: Path) -> list[dict[str, Any]]:
    """Nodes the PM GUI may offer an Archive action on.

    Mirrors ``plan_archive``'s gate rather than re-deriving it, so the button
    never appears on something the CLI would refuse.
    """

    from specy_road.bundled_scripts.roadmap_load import compute_rollup_status, load_roadmap

    from specy_road.milestone_lock import locked_node_ids

    nodes = load_roadmap(root)["nodes"]
    rollup = compute_rollup_status(nodes)
    locked = locked_node_ids(nodes)
    out = []
    for n in nodes:
        nid = n.get("id")
        if isinstance(nid, str) and rollup.get(nid) == "Complete" and nid not in locked:
            out.append({"node_id": nid, "title": n.get("title") or ""})
    return out


def _auto_settings(root: Path) -> tuple[bool, int]:
    """``(enabled, older_than_days)`` from the saved ``pm_gui`` preferences."""
    try:
        from specy_road.bundled_scripts.roadmap_gui_lib import load_settings

        pm = load_settings(root).get("pm_gui") or {}
    except Exception:  # noqa: BLE001 - a settings problem must not break the list
        return False, DEFAULT_AUTO_DAYS
    days = pm.get("auto_archive_after_days")
    try:
        days = max(1, int(days))
    except (TypeError, ValueError):
        days = DEFAULT_AUTO_DAYS
    return pm.get("auto_archive_completed") is True, days


def _api_archives_list() -> dict[str, Any]:
    root = get_repo_root()
    enabled, days = _auto_settings(root)
    # Surfaced, never acted on automatically: archiving moves files, so the
    # preference decides what the drawer OFFERS, and the operator still clicks.
    # The scan walks git history, so it is the most failure-prone part of this
    # response — and the least important. Never let it take down the listing.
    suggestions: list[dict[str, str]] = []
    if enabled:
        try:
            suggestions = [
                {"node_id": nid, "completed_at": done}
                for nid, done in auto_archive_candidates(root, older_than_days=days)
            ]
        except Exception:  # noqa: BLE001 - suggestions are a convenience
            suggestions = []
    return {
        "records": index_records(load_archive_index(root)),
        "eligible": _eligible(root),
        "auto": {
            "enabled": enabled,
            "older_than_days": days,
            "candidates": suggestions,
        },
    }


def _api_archive_get(archive_id: str) -> dict[str, Any]:
    return _record_or_404(get_repo_root(), archive_id)


def _api_archive_nodes(archive_id: str) -> dict[str, Any]:
    """Browse a shallow archive's nodes.

    Deep archives answer with their summary and ``browsable: false`` rather
    than unpacking a bundle to satisfy a page render.
    """
    root = get_repo_root()
    rec = _record_or_404(root, archive_id)
    chunk = rec.get("chunk")
    if rec.get("depth") == "deep" or not isinstance(chunk, str):
        return {
            "browsable": False,
            "depth": rec.get("depth"),
            "nodes": rec.get("nodes_summary") or [],
        }

    from specy_road.bundled_scripts.roadmap_chunk_utils import load_json_chunk

    return {
        "browsable": True,
        "depth": "shallow",
        "nodes": load_json_chunk(root / chunk),
    }


def _api_archive_preview(body: ArchiveCreateBody) -> dict[str, Any]:
    """Dry run: what an archive of ``node_id`` would move. No writes."""
    try:
        plan = plan_archive(get_repo_root(), body.node_id, force=body.force)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"archive_id": plan.archive_id, "summary": plan_summary(plan)}


def _api_archive_create(
    body: ArchiveCreateBody,
    _pm: None = Depends(require_pm_gui_write_header),
) -> dict[str, Any]:
    root = get_repo_root()
    try:
        rec = archive_node(root, body.node_id, force=body.force)
        if body.deep:
            rec = deepen_archive(root, rec["archive_id"])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    _reexport_roadmap_md(root)
    return rec


def _api_archive_auto(
    body: ArchiveAutoBody,
    _pm: None = Depends(require_pm_gui_write_header),
) -> dict[str, Any]:
    root = get_repo_root()
    found = auto_archive_candidates(root, older_than_days=body.older_than_days)
    if body.dry_run:
        return {
            "dry_run": True,
            "candidates": [{"node_id": n, "completed_at": c} for n, c in found],
        }
    archived = []
    for node_id, _completed in found:
        try:
            archived.append(archive_node(root, node_id))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
    if archived:
        _reexport_roadmap_md(root)
    return {"dry_run": False, "archived": archived}


def _api_archive_deepen(
    archive_id: str,
    _pm: None = Depends(require_pm_gui_write_header),
) -> dict[str, Any]:
    try:
        return deepen_archive(get_repo_root(), archive_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


def _api_archive_restore(
    archive_id: str,
    _pm: None = Depends(require_pm_gui_write_header),
) -> dict[str, Any]:
    root = get_repo_root()
    try:
        out = restore_archive(root, archive_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    _reexport_roadmap_md(root)
    return out


def register_archive_routes(api: APIRouter) -> None:
    """Wire the archive handlers onto ``api``.

    Handlers live at module level so this registrar stays under the
    file-limits per-function cap and each one stays directly testable — the
    same arrangement ``gui_app_routes_nodes`` uses.
    """
    api.add_api_route("/archives", _api_archives_list, methods=["GET"])
    api.add_api_route("/archives/preview", _api_archive_preview, methods=["POST"])
    api.add_api_route("/archives/create", _api_archive_create, methods=["POST"])
    api.add_api_route("/archives/auto", _api_archive_auto, methods=["POST"])
    api.add_api_route("/archives/{archive_id}", _api_archive_get, methods=["GET"])
    api.add_api_route(
        "/archives/{archive_id}/nodes", _api_archive_nodes, methods=["GET"]
    )
    api.add_api_route(
        "/archives/{archive_id}/deepen", _api_archive_deepen, methods=["POST"]
    )
    api.add_api_route(
        "/archives/{archive_id}/restore", _api_archive_restore, methods=["POST"]
    )
