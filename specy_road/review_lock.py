"""The per-leaf review lock on ``work/reviews/<NODE_ID>/`` (M21.27, moved out of :mod:`review_record_write` for its
file limit, which re-exports :class:`ReviewRunBusy` and :func:`review_run_lock`).

A reviewer run (``review delegate``, ``prompt --channel cli --run``) holds it for the whole run; a filing
(``review record``, the human approval) takes it for :data:`FILING_WAIT` at most, so it never reads as the run's
own write (:mod:`specy_road.review_write_check`).
"""

from __future__ import annotations

import contextlib
import os
import time
from collections.abc import Iterator
from pathlib import Path

from specy_road import safe_write
from specy_road.review_files import project_of
from specy_road.review_write_check import LOCK_NAME

#: Seconds a filing (``review record``, the human approval) waits for the leaf's lock before it refuses.
FILING_WAIT = 10


def filing_busy(node_id: str) -> str:
    """The refusal when a reviewer run holds the leaf's hand-off directory past :data:`FILING_WAIT`."""
    return f"a reviewer run on {node_id} holds work/reviews/{node_id}/; nothing was written"


class ReviewRunBusy(Exception):
    def __init__(self, node_id: str) -> None:
        super().__init__(f"another reviewer run of {node_id} is in progress; run its reviewers one after another")


@contextlib.contextmanager
def review_run_lock(reviews: Path, wait: float = 0) -> Iterator[None]:
    """One reviewer run or filing per leaf at a time: the hand-off directory is shared, so a second writer's files
    would read as the first run's writes. Retries for up to ``wait`` seconds, then raises :class:`ReviewRunBusy`
    (at once by default, rather than wait for a whole review)."""
    owned = project_of(reviews)
    safe_write.mkdirs(owned, reviews)   # a symlink at work, work/reviews or the node directory is refused here
    deadline = time.monotonic() + wait
    with os.fdopen(safe_write.open_lock(owned, reviews / LOCK_NAME), "a+") as f:
        while True:
            try:
                try:
                    import fcntl   # POSIX; Windows has msvcrt
                    fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except ImportError:
                    import msvcrt
                    msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise ReviewRunBusy(reviews.name) from None
                time.sleep(0.1)
        yield
