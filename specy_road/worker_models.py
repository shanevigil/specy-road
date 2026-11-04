"""The model a worker's turn asked for and the one its harness reported, for the turn's ``usage`` event (M11.33).

A harness that routes models itself (Cursor's Auto, a cascade, its own critic) can run another model than the
``--model`` it was given. The wrapper records the ``--model`` on each ``launched`` event and the model the harness's
``system/init`` line names on its ``started`` event; the turn's ``usage`` event keeps both, and its summary, which
``worker sync`` prints, says when they differ. Split from :mod:`specy_road.worker_runner` for the file limit.
"""

from __future__ import annotations

from typing import Any

from specy_road.worker_state import WorkerEvent


def turn_models(events: list[WorkerEvent]) -> dict[str, str | None]:
    """``requested_model`` and ``observed_model`` from the events since the last ``launched``; ``None`` when unknown."""
    starts = [i for i, e in enumerate(events) if e.type == "launched"]
    turn = events[starts[-1]:] if starts else []
    requested = (turn[0].detail or {}).get("model") if turn else None
    observed = next((str(e.detail["model"]) for e in reversed(turn) if e.type == "started" and e.source == "worker"
                     and (e.detail or {}).get("model")), None)
    return {"requested_model": requested, "observed_model": observed}


def mismatch_note(detail: dict[str, Any]) -> str:
    """The summary suffix when both models are known and differ (ignoring case), else ``""``."""
    told, ran = detail.get("requested_model"), detail.get("observed_model")
    if not told or not ran or str(told).lower() == str(ran).lower():
        return ""
    return f"; model mismatch: told {told}, harness reported {ran}"
