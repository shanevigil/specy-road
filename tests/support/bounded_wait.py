"""Bounded waits for process and race tests.

Logical timeouts use the injectable clock (``specy_road.clock`` or a function's
``clock`` / ``now`` argument). A wait here blocks the caller for at most the
given seconds.
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
