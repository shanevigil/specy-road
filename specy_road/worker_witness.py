"""The prompt-submit hook's witness: record a human's prompt without ever stalling the harness (round 6, F10).

The hook runs inside the harness's prompt pipeline with a vendor timeout
(Cursor: ten seconds), so it must not queue behind a ``delegate`` or a
long transaction on the workers lock. It takes the lock with a bounded
wait; when the lock is not free in time it records nothing and the CLI
exits 0 — a missing witness marks the worker ``possibly_modified_externally``
at reclaim, which is the honest outcome. The match is by harness **and**
session id: two harnesses can hand out the same id, and a prompt must never
be filed under the wrong worker, so an ambiguous match is refused.
"""

from __future__ import annotations

import contextlib
import json
import threading
import time
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

from specy_road.worker_lock import _LOCAL, _THREAD_LOCKS, WorkerError, workers_dir
from specy_road.worker_state import WorkerRecord, list_records, record_path

WITNESS_TIMEOUT = 2.0


def interventions_path(repo_root: Path, worker_id: str) -> Path:
    return record_path(repo_root, worker_id).with_suffix(".interventions.jsonl")


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _try_flock(f, deadline: float) -> bool:
    """``flock`` without blocking, retried until ``deadline``; ``msvcrt`` likewise. Neither: refuse."""
    try:
        import fcntl
    except ImportError:
        fcntl = None
    while True:
        try:
            if fcntl is not None:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            else:
                import msvcrt
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            return True
        except ImportError:
            raise WorkerError("workers need an exclusive file lock (fcntl or msvcrt); this platform has neither") from None
        except OSError:
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.05)


def _unlock(f) -> None:
    try:
        import fcntl
        fcntl.flock(f, fcntl.LOCK_UN)
    except ImportError:
        import msvcrt
        f.seek(0)
        msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)


@contextlib.contextmanager
def try_workers_lock(repo_root: Path, timeout: float = WITNESS_TIMEOUT) -> Iterator[bool]:
    """Like ``workers_lock`` but yields ``False`` instead of waiting past ``timeout``.

    Held the same way (thread lock, then the ``.lock`` file), and registered
    with the re-entrancy depth, so the nested ``workers_lock`` calls inside
    record helpers see it as already taken.
    """
    d = workers_dir(repo_root)
    d.mkdir(parents=True, exist_ok=True)
    key = str(d)
    depth = getattr(_LOCAL, "depth", None) or {}
    _LOCAL.depth = depth
    if depth.get(key, 0) > 0:
        depth[key] += 1
        try:
            yield True
        finally:
            depth[key] -= 1
        return
    deadline = time.monotonic() + timeout
    rlock = _THREAD_LOCKS.setdefault(key, threading.RLock())
    if not rlock.acquire(timeout=timeout):
        yield False
        return
    try:
        with (d / ".lock").open("a+") as f:
            if not _try_flock(f, deadline):
                yield False
                return
            depth[key] = 1
            try:
                yield True
            finally:
                depth[key] = 0
                _unlock(f)
    finally:
        rlock.release()


def match_worker(repo_root: Path, session_id: str, harness: str | None) -> WorkerRecord | None:
    """The one handed-off worker holding ``session_id`` on ``harness``; ``None`` for the broker's own prompts."""
    found = [r for r in list_records(repo_root, active_only=True)
             if r.provider_session_id == session_id and r.lease.get("holder") == "human"
             and (harness is None or r.harness == harness)]
    if len(found) > 1:
        raise WorkerError(f"session {session_id} matches {', '.join(r.worker_id for r in found)} on "
                          f"{harness or 'any harness'}; ambiguous, not recorded")
    return found[0] if found else None


def record_hook_prompt(repo_root: Path, session_id: str, prompt: str, *, harness: str | None = None,
                       timeout: float = WITNESS_TIMEOUT) -> WorkerRecord | None:
    """Append a human prompt seen by a harness hook to the worker that holds that session under a human lease.

    ``None`` when no worker matches **or** the lock was busy for ``timeout``
    seconds: a witness waits a little, never long enough to trip the
    harness's hook timeout.
    """
    with try_workers_lock(repo_root, timeout) as held:   # a reclaim in flight cannot slip between match and append
        if not held:
            return None
        rec = match_worker(repo_root, session_id, harness)
        if rec is None:
            return None   # the broker's own prompts, and closed records, are not interventions
        path = interventions_path(repo_root, rec.worker_id)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"at": _now(), "session_id": session_id, "harness": rec.harness,
                                "prompt": prompt}) + "\n")   # verbatim
    return rec
