"""Read-only worker routes for the PM GUI's Workers drawer.

The records and event logs live in the main worktree's ``work/.workers/``
(gitignored; ``docs/orchestration-workers.md``). These routes only read
them: no stall sweep, no ack, no lock — the coordinator's commands are the
writers. Phase durations and usage totals are the same arithmetic as
``specy-road worker timeline`` and ``worker usage``.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from specy_road.bundled_scripts.worker_cli_render import timeline, usage
from specy_road.gui_app_helpers import get_repo_root
from specy_road.worker_reconcile import sync_marks
from specy_road.worker_state import WorkerError, events_since, list_records, load_record


def _last_event(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not events:
        return None
    e = events[-1]
    return {k: e.get(k) for k in ("seq", "at", "type", "source", "summary")}


def _row(rec, events: list[dict[str, Any]]) -> dict[str, Any]:
    total = usage([(rec, events)])["total"]
    return {"worker_id": rec.worker_id, "node_id": rec.node_id, "harness": rec.harness, "model": rec.model,
            "state": rec.state, "attempt": rec.attempt, "flags": list(rec.flags), "updated": rec.updated,
            "last_event": _last_event(events), "total_cost_usd": total["cost_usd"],
            "cost_is_estimate": total["cost_is_estimate"]}


def _api_workers() -> dict[str, Any]:
    root = get_repo_root()
    rows = [_row(r, [e.to_dict() for e in events_since(root, r.worker_id)]) for r in list_records(root)]
    return {"workers": rows}


def _api_worker_events(worker_id: str) -> dict[str, Any]:
    root = get_repo_root()
    try:
        rec = load_record(root, worker_id)
    except WorkerError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    events = [e.to_dict() for e in events_since(root, worker_id)]
    return {**_row(rec, events), "events": events,
            "phases": timeline(rec, events, sync_marks(root).get(worker_id))["phases"],
            "usage": usage([(rec, events)])["total"]}


def register_worker_routes(api: APIRouter) -> None:
    api.get("/workers")(_api_workers)
    api.get("/workers/{worker_id}/events")(_api_worker_events)
