"""Slot checks behind ``specy-road worker``: dead wrappers, stalled workers, and the ``max_workers`` cap (slice 7c).

Split from :mod:`specy_road.worker_ops` for the file limit; callers reach
these through that module.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from specy_road.orchestration_config import DEFAULT_POLICY
from specy_road.orchestration_pinned import pinned_config
from specy_road.worker_lease import max_workers, slot_error
from specy_road.worker_orphans import holding_slots
from specy_road.worker_process import wrapper_gone
from specy_road.worker_state import (
    FLAG_STALLED,
    WorkerRecord,
    add_flag,
    append_event,
    clear_flag,
    events_since,
    list_records,
    workers_lock,
)


def sweep_dead_wrappers(repo_root: Path) -> list[WorkerRecord]:
    """Close every ``running``/``starting`` record whose wrapper is gone, on any leaf; returns those closed."""
    return [r for r in list_records(repo_root, active_only=True) if _wrapper_gone(repo_root, r)]


def sweep_stalled(repo_root: Path, *, now: datetime | None = None) -> list[WorkerRecord]:
    """Flag each ``running`` worker silent for ``policy.stall_after_seconds`` with one ``stalled`` event per
    silence (the wrapper's next output write clears the flag; so does leaving ``running``); returns those flagged."""
    config, _err = pinned_config(repo_root)   # unreadable: the default threshold, still a signal
    limit = int((config.get("policy") or {}).get("stall_after_seconds", DEFAULT_POLICY["stall_after_seconds"]))
    now = now or datetime.now(timezone.utc)
    out = []
    with workers_lock(repo_root):
        for rec in list_records(repo_root):   # failed and terminated too: a closed worker keeps no stall
            silent = (int((now - datetime.fromisoformat(rec.last_output_at)).total_seconds())
                      if rec.state == "running" and rec.last_output_at else None)
            if silent is None or silent < limit:
                if FLAG_STALLED in rec.flags:
                    clear_flag(repo_root, rec, FLAG_STALLED)
                continue
            if FLAG_STALLED in rec.flags:
                continue
            last = next((e.summary for e in reversed(events_since(repo_root, rec.worker_id)) if e.source == "worker"), None)
            append_event(repo_root, rec, "stalled", source="system",
                         summary=f"no output for {silent}s (policy.stall_after_seconds {limit}); last: {last or '-'}",
                         detail={"silent_seconds": silent, "last_output_at": rec.last_output_at, "last_summary": last})
            add_flag(repo_root, rec, FLAG_STALLED)
            out.append(rec)
    return out


def _slot_or_existing(repo_root: Path, node_id: str, *, own: str | None = None,
                      foreign: list[str] | None = None) -> WorkerRecord | None:
    """Under the lock: the leaf's live worker other than ``own``, else ``None`` once a ``max_workers`` slot is free;
    counted are every other active record (linked worktrees share this directory) and ``foreign`` lease refs
    (``None``: not read yet, so only the leaf's own worker is looked for, and nothing is counted). An ``idle`` or
    ``completed`` record whose leaf is over (unclaimed and Complete at every integration ref, M11.57) is not counted."""
    sweep_dead_wrappers(repo_root)   # a dead wrapper on another leaf must not hold a slot
    active = [r for r in list_records(repo_root, active_only=True) if r.worker_id != own]
    if existing := next((r for r in active if r.node_id == node_id), None):
        return existing
    if foreign is None:
        return None
    held = holding_slots(repo_root, active)   # a held worker whose leaf is over frees its slot (M11.57)
    if len(held) + len(foreign) >= (limit := max_workers(repo_root)):
        raise slot_error(held, foreign, limit)
    return None


def _wrapper_gone(repo_root: Path, rec: WorkerRecord) -> bool:
    """A ``running``/``starting`` record with no live wrapper (nor harness group) is closed: the leaf is free again."""
    return wrapper_gone(repo_root, rec)
