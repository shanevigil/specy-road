"""Slot checks behind ``specy-road worker``: dead wrappers, stalled workers and their recovery (M22.39), and the
``max_workers`` cap (slice 7c).

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
    FLAG_NEEDS_PERSON,
    FLAG_ORPHAN,
    FLAG_STALLED,
    WorkerError,
    WorkerRecord,
    add_flag,
    append_event,
    clear_flag,
    events_since,
    list_records,
    load_record,
    mutate,
    require_writer,
    workers_dir,
    workers_lock,
)


def sweep_dead_wrappers(repo_root: Path) -> list[WorkerRecord]:
    """Close every ``running``/``starting`` record whose wrapper is gone, on any leaf; returns those closed."""
    return [r for r in list_records(repo_root, active_only=True) if _wrapper_gone(repo_root, r)]


#: Recoveries one worker gets when ``policy.max_fix_rounds`` is unset (M22.39).
DEFAULT_RECOVERIES = 3
#: Events that start a follow-up turn (``_send`` writes ``message``, the wrapper ``resumed``), before the new
#: wrapper writes its own ``last_output_at``; and those that start the first turn.
_TURN_EVENTS = frozenset({"message", "resumed"})
_FIRST_EVENTS = frozenset({"started", "launched"})


def _policy(repo_root: Path) -> dict:
    config, _err = pinned_config(repo_root)   # unreadable: the defaults, still a signal
    return config.get("policy") or {}


def silent_seconds(repo_root: Path, rec: WorkerRecord, now: datetime) -> int | None:
    """Seconds a ``running`` worker has been silent; ``None`` for any other state. One rule (M22.39): silence runs
    from the newest of its last output and the event that started its current follow-up turn, so a resumed or
    recovered turn never inherits the last turn's silence; with neither, from the first turn's launch."""
    if rec.state != "running":
        return None
    events = events_since(repo_root, rec.worker_id)
    turn = next((e.at for e in reversed(events) if e.type in _TURN_EVENTS), None)
    stamps = [datetime.fromisoformat(t) for t in (rec.last_output_at, turn) if t]
    since = max(stamps) if stamps else datetime.fromisoformat(
        next((e.at for e in reversed(events) if e.type in _FIRST_EVENTS), rec.created))
    return int((now - since).total_seconds())


def last_output(repo_root: Path, worker_id: str) -> str | None:
    """The summary of the worker's last event parsed from the harness."""
    return next((e.summary for e in reversed(events_since(repo_root, worker_id)) if e.source == "worker"), None)


def sweep_stalled(repo_root: Path, *, now: datetime | None = None) -> list[WorkerRecord]:
    """Flag each ``running`` worker silent for ``policy.stall_after_seconds`` with one ``stalled`` event per
    silence (the wrapper's next output write clears the flag; so does leaving ``running``); returns those flagged.
    A worker that never wrote output is measured from its launch (M22.39)."""
    limit = int(_policy(repo_root).get("stall_after_seconds", DEFAULT_POLICY["stall_after_seconds"]))
    now = now or datetime.now(timezone.utc)
    out = []
    with workers_lock(repo_root):
        for rec in list_records(repo_root):   # failed and terminated too: a closed worker keeps no stall
            silent = silent_seconds(repo_root, rec, now)
            if silent is None or silent < limit:
                for flag in (FLAG_STALLED, FLAG_NEEDS_PERSON):
                    if flag in rec.flags:
                        clear_flag(repo_root, rec, flag)
                continue
            if FLAG_STALLED in rec.flags:
                continue
            last = last_output(repo_root, rec.worker_id)
            append_event(repo_root, rec, "stalled", source="system",
                         summary=f"no output for {silent}s (policy.stall_after_seconds {limit}); last: {last or '-'}",
                         detail={"silent_seconds": silent, "last_output_at": rec.last_output_at, "last_summary": last})
            add_flag(repo_root, rec, FLAG_STALLED)
            out.append(rec)
    return out


def recovery_pending(repo_root: Path, rec: WorkerRecord) -> bool:
    """A counted recovery whose resume never started: its ``recovery`` event is newer than the last ``message``
    (``_send`` writes one before every spawn), so the turn was ended and then a refusal (an unreachable lease
    remote, a launch check, the slot or branch check) stopped the resume. The next ``recover`` finishes it without
    counting it again. Limit: a spawn that fails after its ``message`` is logged counts as started."""
    for e in reversed(events_since(repo_root, rec.worker_id)):
        if e.type == "message":
            return False
        if (e.detail or {}).get("recovery"):
            return rec.state != "terminated"   # failed is how an ended turn is left; it keeps its session
    return False


def stalled_workers(repo_root: Path, *, now: datetime | None = None) -> list[dict]:
    """After a sweep, each stalled worker and each pending recovery: id, leaf, seconds silent (``None`` once the
    turn is ended), recoveries used and allowed, ``needs_person`` and ``pending``."""
    now = now or datetime.now(timezone.utc)
    sweep_stalled(repo_root, now=now)
    limit = recovery_limit(repo_root)
    return [{"worker_id": r.worker_id, "node_id": r.node_id, "silent_seconds": silent_seconds(repo_root, r, now),
             "recoveries": r.recoveries or 0, "recovery_limit": limit, "needs_person": FLAG_NEEDS_PERSON in r.flags,
             "pending": pending}
            for r in list_records(repo_root)
            if (pending := recovery_pending(repo_root, r)) or FLAG_STALLED in r.flags]


def stall_lines(stalls: list[dict]) -> list[str]:
    """One line per stalled worker or pending recovery, with how long it has been silent and what to run."""
    return [(f"recovery pending: {s['worker_id']} ({s['node_id']}) recovery {s['recoveries']}/{s['recovery_limit']} "
             "ended its turn but the resume did not start" if s["pending"] else
             f"stalled: {s['worker_id']} ({s['node_id']}) silent {s['silent_seconds']}s, recoveries "
             f"{s['recoveries']}/{s['recovery_limit']}") + " — "
            + ("needs a person (`worker status`, then `worker terminate` or wait)" if s["needs_person"]
               else f"`specy-road worker recover {s['worker_id']}`") for s in stalls]


def recovery_limit(repo_root: Path) -> int:
    """Recoveries per worker: ``policy.max_fix_rounds``, else :data:`DEFAULT_RECOVERIES`."""
    return int(_policy(repo_root).get("max_fix_rounds") or DEFAULT_RECOVERIES)


def _next_recovery(repo_root: Path, rec: WorkerRecord) -> int:
    """The number the next recovery takes; past :func:`recovery_limit`, flag ``needs_person`` (one event naming the
    last output) and raise."""
    limit, last = recovery_limit(repo_root), last_output(repo_root, rec.worker_id) or "-"
    if (rec.recoveries or 0) < limit:
        return (rec.recoveries or 0) + 1
    if FLAG_NEEDS_PERSON not in rec.flags:
        append_event(repo_root, rec, "error", source="system",
                     summary=f"stalled after {limit} recoveries; needs a person; last output: {last}")
        add_flag(repo_root, rec, FLAG_NEEDS_PERSON)
    raise WorkerError(f"{rec.worker_id} needs a person: stalled after {limit} recoveries "
                      f"(policy.max_fix_rounds, default {DEFAULT_RECOVERIES}); last output: {last}")


def recover(repo_root: Path, worker_id: str, *, offline: bool = False,
            now: datetime | None = None) -> WorkerRecord:
    """``worker recover``: end a stalled worker's process group, keep its worktree and commits, and resume its
    native session with the continue prompt. One shot under the workers lock, so two recoveries never overlap;
    refused (nothing ended) when the worker is not stalled, another live worker holds its leaf, or it cannot be
    resumed; past :func:`recovery_limit` it is flagged ``needs_person`` with its last output named (M22.39).
    A recovery is counted when it ends the turn; one whose resume was then refused stays pending
    (:func:`recovery_pending`), and the next call finishes it, online or ``--offline``, without counting it again."""
    from specy_road.worker_adapters import adapter_for   # noqa: PLC0415
    from specy_road.worker_ops_message import CONTINUE_PROMPT, _send   # noqa: PLC0415 — it imports this module
    from specy_road.worker_process import require_branch   # noqa: PLC0415

    with workers_lock(repo_root):
        sweep_stalled(repo_root, now=now)
        rec = load_record(repo_root, worker_id)
        pending = recovery_pending(repo_root, rec)
        if not pending and FLAG_STALLED not in rec.flags:
            raise WorkerError(f"{worker_id} is not stalled ({rec.state}); nothing to recover")
        other = next((r for r in list_records(repo_root, active_only=True)
                      if r.node_id == rec.node_id and r.worker_id != worker_id), None)
        if other:
            raise WorkerError(f"{rec.node_id} already has an active worker ({other.worker_id}, {other.state}); "
                              f"{worker_id} is left as it is")
        n = None if pending else _next_recovery(repo_root, rec)
        require_writer(rec)
        if not adapter_for(rec.harness).caps.resume or not rec.provider_session_id:
            raise WorkerError(f"{worker_id} has no native session it can resume; it is left running — "
                              "`worker terminate` it and `worker delegate --rework` instead")
        require_branch(rec)
        if n:   # counted before anything can fail, and no longer stalled: the new turn's silence starts at its message
            mutate(repo_root, rec, lambda r: r.__dict__.update(recoveries=n, flags=[f for f in r.flags if f != FLAG_STALLED]))
            append_event(repo_root, rec, "error", source="system", detail={"recovery": n},
                         summary=f"stalled; recovery {n} of {recovery_limit(repo_root)}: ending its processes and "
                                 f"resuming; last output: {last_output(repo_root, worker_id) or '-'}")
        _end_turn(repo_root, load_record(repo_root, worker_id))
        return _send(repo_root, load_record(repo_root, worker_id), CONTINUE_PROMPT, "recover", offline,
                     no_queue=True)


def _end_turn(repo_root: Path, rec: WorkerRecord) -> None:
    """End the stalled turn as ``terminate`` does, minus closing the record: signal the process group (when anything
    of it lives) and, only once it is confirmed gone (``kill_group`` raises otherwise), drop what that turn left
    behind: the ``wrapper_gone_harness_alive`` flag and the worker's own presence session (``<user>-s<pgid>``).
    The worktree, its commits and its uncommitted files are untouched."""
    from specy_road.session_presence import current_user   # noqa: PLC0415
    from specy_road.worker_ops_lifecycle import _end_worker_session   # noqa: PLC0415 — terminate's own cleanup
    from specy_road.worker_process import kill_group, process_alive   # noqa: PLC0415

    agent = f"{current_user()}-s{rec.pgid}" if rec.pgid else None   # read before the new turn replaces the pgid
    if process_alive(rec, repo_root):
        kill_group(rec, repo_root)
    clear_flag(repo_root, rec, FLAG_ORPHAN)
    if agent:
        _end_worker_session(repo_root, agent, Path(rec.worktree))


def recover_stalled(repo_root: Path) -> list[dict]:
    """Recover each stalled worker not already waiting for a person: what ``grind-session`` runs on its loop.
    One entry per worker tried: ``worker_id``, ``node_id``, ``outcome`` (``recovered``, ``needs_person`` or
    ``refused``) and ``detail``."""
    out: list[dict] = []
    if not workers_dir(repo_root).is_dir():   # no worker was ever launched here: nothing to sweep or create
        return out
    for s in stalled_workers(repo_root):
        if s["needs_person"]:
            continue
        try:
            recover(repo_root, s["worker_id"])
            outcome, detail = "recovered", ("finished a pending recovery" if s["pending"]
                                            else f"resumed after {s['silent_seconds']}s of silence")
        except Exception as e:  # noqa: BLE001 — one worker's refusal must not stop the loop
            outcome = "needs_person" if "needs a person" in str(e) else "refused"
            detail = str(e)
        out.append({"worker_id": s["worker_id"], "node_id": s["node_id"], "outcome": outcome, "detail": detail})
    return out


def _slot_or_existing(repo_root: Path, node_id: str, *, own: str | None = None,
                      foreign: list[str] | None = None) -> WorkerRecord | None:
    """Under the lock: the leaf's live worker other than ``own``, else ``None`` once a ``max_workers`` slot is free;
    counted are every other active record (linked worktrees share this directory) and ``foreign`` lease refs
    (``None``: not read yet, so only the leaf's own worker is looked for, and nothing is counted). Counted states
    are ``starting``, ``running``, ``idle`` and ``paused_by_limit``; an idle or paused record whose leaf is over
    (unclaimed or Complete at every integration ref, or its worktree gone; M11.57) is not, and ``completed``,
    ``failed`` and ``terminated`` never are (M15.26)."""
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
