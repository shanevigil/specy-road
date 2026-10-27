"""The human lease: ``worker handoff`` / ``reclaim`` (slice 7c); the hook witness is :mod:`worker_witness`.

Split from :mod:`specy_road.worker_ops` for the file limit; the CLI reaches
these through that module. Each transition runs under the workers lock as
one transaction, so a second ``reclaim`` sees the lease already returned
and a hook append cannot slip between a reclaim's read and its write.
``reclaim`` moves the record (epoch, lease, state, flag) in **one** write
before it appends its events, so a crash and a retry cannot count the same
intervention twice; a retry after that write only repairs the missing events.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from specy_road.git_subprocess import git_text
from specy_road.worker_adapters import Unsupported, adapter_for
from specy_road.worker_runner import pid_alive
from specy_road.worker_sessions import check_session_id, render_command
from specy_road.worker_state import (
    FLAG_EXTERNAL,
    TERMINAL_STATES,
    WorkerError,
    WorkerRecord,
    append_event,
    events_since,
    load_record,
    mutate,
    require_writer,
    set_state,
    take_checkpoint,
    workers_lock,
)
from specy_road.worker_witness import interventions_path, record_hook_prompt  # noqa: F401 — re-exported

CLOSED_STATES = TERMINAL_STATES


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def handoff(repo_root: Path, worker_id: str) -> tuple[WorkerRecord, list[str]]:
    """Lease the worker to a human; returns the native resume command."""
    with workers_lock(repo_root):
        return _handoff_locked(repo_root, load_record(repo_root, worker_id))


def _handoff_locked(repo_root: Path, rec: WorkerRecord) -> tuple[WorkerRecord, list[str]]:
    if rec.lease.get("holder") == "human":
        sid = check_session_id(rec.harness, rec.provider_session_id)
        return rec, adapter_for(rec.harness).human_resume(sid, Path(rec.worktree))
    require_writer(rec)
    if rec.state in ("running", "starting") and not pid_alive(rec.pid, rec.worker_id):
        append_event(repo_root, rec, "error", source="system",
                     summary=f"wrapper pid {rec.pid or '-'} is gone without recording an exit; marked failed")
        set_state(repo_root, rec, "failed", pid=None)
    if rec.state in CLOSED_STATES:
        raise WorkerError(f"{rec.worker_id} is {rec.state}; nothing to hand off")
    if pid_alive(rec.pid, rec.worker_id):
        raise WorkerError(f"{rec.worker_id} is running (pid {rec.pid}); wait for idle or terminate first")
    adapter = adapter_for(rec.harness)
    if not adapter.caps.handoff or not rec.provider_session_id:
        raise Unsupported(f"unsupported by {rec.harness}: handoff (no native session to resume)")
    cmd = adapter.human_resume(check_session_id(rec.harness, rec.provider_session_id), Path(rec.worktree))
    take_checkpoint(repo_root, rec)
    # Prompts recorded before this line are an earlier lease's, whatever
    # their timestamp (the clock has one-second resolution).
    seen = _hook_lines(repo_root, rec)

    def move(r: WorkerRecord) -> None:   # one write: the lease never changes hands without its checkpoint
        r.checkpoint["interventions_seen"] = seen
        r.lease = {"holder": "human", "since": _now()}
        r.state = "handed_off"
    mutate(repo_root, rec, move)
    append_event(repo_root, rec, "handoff", source="orchestrator", authority="orchestrator",
                 summary=f"handed off; resume with: {render_command(cmd)} (in {rec.worktree})")
    return rec, cmd


def _hook_lines(repo_root: Path, rec: WorkerRecord) -> int:
    path = interventions_path(repo_root, rec.worker_id)
    return len(path.read_text(encoding="utf-8").splitlines()) if path.is_file() else 0


def _hook_prompts(repo_root: Path, rec: WorkerRecord, skip: int) -> list[dict[str, Any]]:
    """The hook-recorded prompts after the first ``skip`` lines (those predate the hand-off)."""
    path = interventions_path(repo_root, rec.worker_id)
    if not path.is_file():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines()[skip:]:
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if isinstance(d, dict):
            out.append(d)
    return out


def _diff_stat(worktree: Path, since_sha: str | None) -> str:
    """``git diff --stat`` since the checkpoint plus the untracked files, which a diff omits."""
    stat = (git_text(["diff", "--stat", since_sha], worktree) or "") if since_sha else ""
    new = git_text(["ls-files", "--others", "--exclude-standard"], worktree) or ""
    return "\n".join(x for x in [stat, *(f" {p} | new" for p in new.splitlines() if p.strip())] if x)


def reclaim(repo_root: Path, worker_id: str, note: str = "") -> tuple[WorkerRecord, dict[str, Any]]:
    with workers_lock(repo_root):   # one transaction: a second reclaim sees the lease already returned
        return _reclaim_locked(repo_root, load_record(repo_root, worker_id), note)


def _events_behind(repo_root: Path, rec: WorkerRecord) -> bool:
    """The record's epoch moved but the matching ``intervention`` event never landed: a crash mid-reclaim."""
    logged = sum(1 for e in events_since(repo_root, rec.worker_id) if e.type == "intervention")
    return rec.instruction_epoch > logged


def _gather(repo_root: Path, rec: WorkerRecord, note: str) -> tuple[dict[str, Any], str, list[str]]:
    cp = rec.checkpoint or {}
    prompts = _hook_prompts(repo_root, rec, int(cp.get("interventions_seen") or 0))
    stat = _diff_stat(Path(rec.worktree), cp.get("git_head"))
    pre_existing = sorted(set(cp.get("dirty_paths") or []))
    if pre_existing:
        stat += "\n(already dirty at hand-off, not the human's: " + ", ".join(pre_existing) + ")"
    heard = [str(p.get("prompt", "")) for p in prompts]          # verbatim: the hook stores the whole prompt
    shown = [h[:200] for h in heard]
    summary = (f"human direction ({len(heard)} prompt(s) recorded by hook): " + " | ".join(shown)
               if heard else "human session returned without hook evidence")
    if note:
        summary += f" — note: {note}"
    detail = {"prompts": heard, "diff_stat": stat, "checkpoint": cp, "pre_existing_dirty": pre_existing}
    return detail, summary, heard


def _reclaim_locked(repo_root: Path, rec: WorkerRecord, note: str) -> tuple[WorkerRecord, dict[str, Any]]:
    repairing = rec.lease.get("holder") != "human" and _events_behind(repo_root, rec)
    if rec.lease.get("holder") != "human" and not repairing:
        raise WorkerError(f"{rec.worker_id} is not handed off (lease: {rec.lease.get('holder')})")
    detail, summary, heard = _gather(repo_root, rec, note)
    if not repairing:
        def move(r: WorkerRecord) -> None:   # one write: epoch, flag, lease and state together
            r.instruction_epoch += 1
            if not heard and FLAG_EXTERNAL not in r.flags:
                r.flags.append(FLAG_EXTERNAL)
            r.lease = {"holder": "broker", "since": _now()}
            r.state = "idle"
        mutate(repo_root, rec, move)
    else:
        summary += " (events repaired after an interrupted reclaim)"
    append_event(repo_root, rec, "intervention", source="hook" if heard else "human",
                 authority="human_authoritative", summary=summary, detail=detail)
    append_event(repo_root, rec, "reclaim", source="orchestrator", authority="orchestrator",
                 summary=f"lease back to broker; epoch {rec.instruction_epoch}")
    return rec, detail
