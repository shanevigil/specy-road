"""The human lease: ``worker handoff`` / ``reclaim`` and the prompt-submit hook (slice 7c).

Split from :mod:`specy_road.worker_ops` for the file limit; the CLI reaches
these through that module. Each transition runs under the workers lock as
one transaction, so a second ``reclaim`` sees the lease already returned
and a hook append cannot slip between a reclaim's read and its write.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from specy_road.git_subprocess import git_text
from specy_road.worker_adapters import Unsupported, adapter_for
from specy_road.worker_runner import pid_alive
from specy_road.worker_state import (
    FLAG_EXTERNAL,
    TERMINAL_STATES,
    WorkerError,
    WorkerRecord,
    add_flag,
    append_event,
    list_records,
    load_record,
    mutate,
    record_intervention,
    record_path,
    require_writer,
    set_lease,
    set_state,
    take_checkpoint,
    workers_lock,
)

CLOSED_STATES = TERMINAL_STATES


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def interventions_path(repo_root: Path, worker_id: str) -> Path:
    return record_path(repo_root, worker_id).with_suffix(".interventions.jsonl")


def handoff(repo_root: Path, worker_id: str) -> tuple[WorkerRecord, list[str]]:
    """Lease the worker to a human; returns the native resume command."""
    with workers_lock(repo_root):
        return _handoff_locked(repo_root, load_record(repo_root, worker_id))


def _handoff_locked(repo_root: Path, rec: WorkerRecord) -> tuple[WorkerRecord, list[str]]:
    if rec.lease.get("holder") == "human":
        return rec, adapter_for(rec.harness).human_resume(rec.provider_session_id or "", Path(rec.worktree))
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
    cmd = adapter.human_resume(rec.provider_session_id, Path(rec.worktree))
    take_checkpoint(repo_root, rec)
    # Prompts recorded before this line are an earlier lease's, whatever
    # their timestamp (the clock has one-second resolution).
    seen = _hook_lines(repo_root, rec)
    mutate(repo_root, rec, lambda r: r.checkpoint.__setitem__("interventions_seen", seen))
    set_lease(repo_root, rec, "human")
    set_state(repo_root, rec, "handed_off")
    append_event(repo_root, rec, "handoff", source="orchestrator", authority="orchestrator",
                 summary=f"handed off; resume with: {' '.join(cmd)} (in {rec.worktree})")
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


def _reclaim_locked(repo_root: Path, rec: WorkerRecord, note: str) -> tuple[WorkerRecord, dict[str, Any]]:
    if rec.lease.get("holder") != "human":
        raise WorkerError(f"{rec.worker_id} is not handed off (lease: {rec.lease.get('holder')})")
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
    record_intervention(repo_root, rec, summary, source="hook" if heard else "human", detail=detail)
    if not heard:
        add_flag(repo_root, rec, FLAG_EXTERNAL)
    set_lease(repo_root, rec, "broker")
    set_state(repo_root, rec, "idle")
    append_event(repo_root, rec, "reclaim", source="orchestrator", authority="orchestrator",
                 summary=f"lease back to broker; epoch {rec.instruction_epoch}")
    return rec, detail


def record_hook_prompt(repo_root: Path, session_id: str, prompt: str) -> WorkerRecord | None:
    """Append a human prompt seen by a harness hook to the worker that holds that session under a human lease."""
    with workers_lock(repo_root):   # a reclaim in flight cannot slip between the match and the append
        rec = next((r for r in list_records(repo_root, active_only=True)
                    if r.provider_session_id == session_id and r.lease.get("holder") == "human"), None)
        if rec is None:
            return None   # the broker's own prompts, and closed records, are not interventions
        path = interventions_path(repo_root, rec.worker_id)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"at": _now(), "session_id": session_id, "prompt": prompt}) + "\n")   # verbatim
    return rec
