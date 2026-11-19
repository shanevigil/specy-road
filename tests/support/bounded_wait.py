"""Bounded waits for process and race tests.

Logical timeouts use the injectable clock (``specy_road.clock`` or a function's
``clock`` / ``now`` argument). A race wait returns only when the overlap is
visible: an event, or a condition ``wait_until`` polls. ``pause`` is the poll
interval inside that wait. A fixed delay does not establish an overlap.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable


def pause(seconds: float) -> None:
    """Wait up to ``seconds`` for a process or a race."""
    if seconds > 0:
        threading.Event().wait(seconds)


def wait_until(
    predicate: Callable[[], bool],
    timeout: float = 5.0,
    interval: float = 0.05,
    message: str = "condition not met",
) -> None:
    """Poll ``predicate`` until it holds or ``timeout`` elapses."""
    deadline = time.monotonic() + timeout
    while True:
        if predicate():
            return
        if time.monotonic() >= deadline:
            raise AssertionError(message)
        pause(min(interval, max(0.0, deadline - time.monotonic())))


def counting_lock(real: Callable, arrived: threading.Event, need: int = 2) -> Callable:
    """A lock stand-in that sets ``arrived`` once ``need`` callers reach it.

    The count is taken before the real lock, so a caller blocked behind a holder
    still counts. The test waits for ``arrived`` before it releases that holder
    or lets a gated body continue.
    """
    state = {"n": 0}
    guard = threading.Lock()

    def wrapped(repo_root):
        with guard:
            state["n"] += 1
            if state["n"] >= need:
                arrived.set()
        return real(repo_root)

    return wrapped
