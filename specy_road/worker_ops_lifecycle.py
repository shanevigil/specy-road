"""``worker terminate`` and ``worker adopt``: the record transitions that launch no harness (slice 7c).

Split from :mod:`specy_road.worker_ops` for the file limit; callers reach
these through that module.
"""

from __future__ import annotations

from pathlib import Path

from specy_road.worker_lease import lease_adopted, release_lease
from specy_road.worker_ops_launch import _target, _worktree_for
from specy_road.worker_process import kill_group, process_alive
from specy_road.worker_sessions import check_session_id
from specy_road.worker_state import (
    FLAG_UNDELIVERED,
    WorkerError,
    WorkerRecord,
    active_for_node,
    append_event,
    clear_flag,
    create_record,
    list_records,
    load_record,
    mutate,
    set_state,
    take_checkpoint,
    workers_lock,
)


def terminate(repo_root: Path, worker_id: str) -> WorkerRecord:
    with workers_lock(repo_root):
        rec = _terminate_locked(repo_root, load_record(repo_root, worker_id))
    release_lease(repo_root, rec.worker_id)   # a network call: after the lock
    return rec


def _terminate_locked(repo_root: Path, rec: WorkerRecord) -> WorkerRecord:
    if rec.state == "terminated":
        return rec
    if rec.lease.get("holder") == "human":
        raise WorkerError(f"{rec.worker_id} is handed off to a human; `worker reclaim` first")
    summary = "terminated by the coordinator"
    if rec.lease.get("holder") == "native":
        summary = "record closed; the adopted native session was not signalled (observe-only lease)"
    elif process_alive(rec, repo_root):
        # The wrapper is a session leader (start_new_session), so its process
        # group holds the harness and everything the harness spawned; the
        # group is signalled and confirmed gone even when the wrapper itself died.
        kill_group(rec, repo_root)
    if rec.queued_message:
        mutate(repo_root, rec, lambda r: setattr(r, "queued_message", None))
        rec, summary = load_record(repo_root, rec.worker_id), f"{summary}; dropped queued follow-up"
    if FLAG_UNDELIVERED in rec.flags:
        clear_flag(repo_root, rec, FLAG_UNDELIVERED)
    set_state(repo_root, rec, "terminated", pid=None)
    append_event(repo_root, rec, "terminated", source="orchestrator", authority="orchestrator", summary=summary)
    return rec


def adopt(repo_root: Path, node_id: str, harness: str, session_id: str, *,
          worktree: Path | None = None, model: str = "unknown") -> WorkerRecord:
    check_session_id(harness, session_id, vendor_syntax=True)   # typed in by the user: the vendor's own shape
    t = _target(repo_root, node_id)
    with workers_lock(repo_root):
        existing = active_for_node(repo_root, node_id)
        if existing:
            raise WorkerError(f"{node_id} already has an active worker ({existing.worker_id}, {existing.state})")
        if any(r.provider_session_id == session_id and r.active for r in list_records(repo_root)):
            raise WorkerError(f"session {session_id} is already a worker")
        wt = _worktree_for(repo_root, str(t.entry["branch"]), str(t.node.get("codename") or node_id), worktree)
        rec = create_record(repo_root, node_id, harness, model, wt, branch=str(t.entry["branch"]), lease="native")
        lease_adopted(repo_root, rec)   # visible to other checkouts before it counts as adopted here
        mutate(repo_root, rec, lambda r: r.__dict__.update(provider_session_id=session_id, state="idle"))
        take_checkpoint(repo_root, rec)
        append_event(repo_root, rec, "adopted", source="orchestrator", authority="orchestrator",
                     summary=f"adopted native {harness} session {session_id}; observe only")
    return rec
