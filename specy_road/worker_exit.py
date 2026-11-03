"""The event a worker's turn ends with, and the reason when its harness failed before saying anything (M11.35).

Split from :mod:`specy_road.worker_runner` for the file limit. A harness that exits non-zero before its first
stream event (an unknown model id answered with an HTTP 404, say) leaves its reason only in the raw log, so the
exit event quotes the last error line the turn wrote there instead of only pointing at the log.
"""

from __future__ import annotations

import re
from pathlib import Path

from specy_road.worker_state import WorkerRecord, append_event, events_since

#: How much of the turn's log tail is read for the reason; a harness that never started prints little.
TAIL_BYTES = 64 * 1024
_ERRORISH = re.compile(r"error|fail|denied|invalid|not found|unknown|\b[45]\d\d\b", re.IGNORECASE)


def streamed(repo_root: Path, worker_id: str) -> bool:
    """True when the harness's output gave an event since the turn's ``launched`` (the wrapper's null usage aside)."""
    events = events_since(repo_root, worker_id)
    start = max((i for i, e in enumerate(events) if e.type == "launched"), default=-1)
    return any(e.source == "worker" and e.type != "usage" for e in events[start + 1:])


def last_error_line(log: Path, start: int = 0) -> str | None:
    """The last line of ``log`` past byte ``start`` that reads like an error, else its last line; wrapper notes skipped."""
    try:
        with log.open("rb") as f:
            f.seek(max(start, f.seek(0, 2) - TAIL_BYTES))
            text = f.read().decode("utf-8", errors="replace")
    except OSError:
        return None
    lines = [s.strip() for s in text.splitlines() if s.strip() and not s.startswith("[wrapper]")]
    return next((s for s in reversed(lines) if _ERRORISH.search(s)), lines[-1] if lines else None)


def exit_event(repo_root: Path, rec: WorkerRecord, code: int, ready: bool, log: Path, log_start: int = 0) -> None:
    """``completion`` on exit 0, else ``error``, with the harness's own reason when it failed before streaming."""
    if code == 0:
        append_event(repo_root, rec, "completion", source="worker",
                     summary=f"exit 0; READY file {'present' if ready else 'missing'}", detail={"exit": 0, "ready": ready})
        return
    detail: dict = {"exit": code, "ready": ready}
    summary = f"exit {code}; see {log.name}"
    why = None if streamed(repo_root, rec.worker_id) else last_error_line(log, log_start)
    if why:
        detail["harness_error"] = why[:2000]
        summary = f"exit {code} before any stream event: {why[:300]}; see {log.name}"
    append_event(repo_root, rec, "error", source="worker", summary=summary, detail=detail)
