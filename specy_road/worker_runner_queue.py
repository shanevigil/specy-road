"""Queued follow-up messages for idle workers (split from worker_runner for the file limit)."""

from __future__ import annotations

from pathlib import Path

from specy_road.worker_state import WorkerError, WorkerRecord, append_event, load_record, mutate, require_writer, workers_lock


def queue_worker_message(repo_root: Path, rec: WorkerRecord, text: str) -> WorkerRecord:
    if not rec.provider_session_id:
        raise WorkerError(f"{rec.worker_id} has no native session id yet; nothing to queue for")
    with workers_lock(repo_root):
        rec = load_record(repo_root, rec.worker_id)
        require_writer(rec)
        prior = rec.queued_message
        mutate(repo_root, rec, lambda r: setattr(r, "queued_message", f"{prior}\n\n{text}" if prior else text))
    verb = "appended" if prior else "queued"
    append_event(repo_root, load_record(repo_root, rec.worker_id), "message_queued", source="orchestrator",
                 authority="orchestrator", summary=f"{verb}: {' '.join(text.split())[:300]}")
    return load_record(repo_root, rec.worker_id)


def deliver_queued_message(repo_root: Path, worker_id: str, *, offline: bool = False) -> WorkerRecord | None:
    from specy_road.worker_ops import _send  # noqa: PLC0415 — ops imports spawn from worker_runner

    with workers_lock(repo_root):   # process_alive and spawn as one transition, like message()
        rec = load_record(repo_root, worker_id)
        text = rec.queued_message
        if not text or rec.state == "terminated":
            return None
        mutate(repo_root, rec, lambda r: setattr(r, "queued_message", None))
        try:
            return _send(repo_root, rec, text, "message", offline)
        except WorkerError as e:
            rec = load_record(repo_root, worker_id)
            if rec.state != "terminated":
                mutate(repo_root, rec, lambda r: setattr(r, "queued_message", text))
            append_event(repo_root, rec, "error", source="system", summary=f"queued message not delivered: {e}")
            raise
