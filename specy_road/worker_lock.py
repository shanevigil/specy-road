"""The workers lock and the error type (split from worker_state for the file limit)."""

from __future__ import annotations

import contextlib
import threading
from collections.abc import Callable, Iterator
from pathlib import Path

from specy_road.review_files import reviews_root

WORKERS_DIRNAME = ".workers"


class WorkerError(Exception):
    """A record is missing, invalid, or the operation is not allowed in its state."""


def workers_dir(repo_root: Path) -> Path:
    return reviews_root(repo_root).parent / WORKERS_DIRNAME


_THREAD_LOCKS: dict[str, threading.RLock] = {}
_LOCAL = threading.local()


@contextlib.contextmanager
def workers_lock(repo_root: Path) -> Iterator[None]:
    """One exclusive lock for every load-modify-save under ``work/.workers/``.

    The wrapper, the coordinator's commands and a hook all write records; a
    read-modify-write without the lock loses the other writer's change
    (``needs_reconcile`` set by ``reconcile`` while the wrapper streams, two
    ``delegate`` calls on one leaf). Re-entrant within a thread, so a mutation
    that appends an event takes it once; an ``RLock`` serialises threads of
    one process and ``flock`` (``msvcrt.locking`` on Windows) serialises
    processes. A platform with neither refuses worker mutations outright
    rather than run them unserialised.
    """
    d = workers_dir(repo_root)
    d.mkdir(parents=True, exist_ok=True)
    key = str(d)
    depth = getattr(_LOCAL, "depth", None) or {}
    _LOCAL.depth = depth
    if depth.get(key, 0) > 0:
        depth[key] += 1
        try:
            yield
        finally:
            depth[key] -= 1
        return
    rlock = _THREAD_LOCKS.setdefault(key, threading.RLock())
    with rlock, (d / ".lock").open("a+") as f:
        unlock = _lock_file(f)
        depth[key] = 1
        try:
            yield
        finally:
            depth[key] = 0
            unlock()


def _lock_file(f) -> Callable[[], None]:
    """Take an exclusive inter-process lock on ``f``; returns the release. Refuses where none exists."""
    try:
        import fcntl
    except ImportError:
        fcntl = None
    if fcntl is not None:
        fcntl.flock(f, fcntl.LOCK_EX)
        return lambda: fcntl.flock(f, fcntl.LOCK_UN)
    try:
        import msvcrt
    except ImportError:
        raise WorkerError("workers need an exclusive file lock (fcntl or msvcrt); this platform has neither") from None
    f.seek(0)
    msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)   # blocks, retrying, until the byte is ours
    return lambda: (f.seek(0), msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1))


