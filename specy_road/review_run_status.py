"""Whether a delegated review run that did not complete was superseded by a record filed later (M15.17).

A ``RUN-<model>.json`` left ``incomplete`` (or never closed) beside a valid ``REVIEW-<model>.md`` filed after it at
the same commit reads as a contradiction in ``review list`` and ``handoff status``: the reviewer's verdict is there,
by another route (``review record``, a ``--resume``, ``prompt --channel cli``). :func:`superseded_by` names that
record, so the run is marked superseded, as a record for another commit is marked stale.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from specy_road.review_files import list_reviews
from specy_road.review_target import same_commit


def _run_time(run: dict[str, Any]) -> float | None:
    """When ``run`` last changed (``ended_at``, else ``started_at``), as a POSIX time; ``None`` when unreadable."""
    raw = run.get("ended_at") or run.get("started_at")
    try:
        at = datetime.fromisoformat(str(raw))
    except ValueError:
        return None
    return (at if at.tzinfo else at.replace(tzinfo=timezone.utc)).timestamp()


def superseded_by(repo_root: Path, node_id: str, run: dict[str, Any]) -> str | None:
    """The name of a valid ``REVIEW-<model>.md`` for ``run``'s model and commit, written no earlier than the run's
    last change, when ``run`` did not complete; else ``None``. Run times are whole seconds, so the comparison is too."""
    if run.get("state") == "complete" or not run.get("commit") or not run.get("model"):
        return None
    since = _run_time(run)
    if since is None:
        return None
    for rec in list_reviews(repo_root, node_id):
        if (rec.ok and rec.path.name == f"REVIEW-{run['model']}.md" and rec.data.get("node_id") == node_id
                and same_commit(repo_root, rec.data.get("commit"), run["commit"])
                and int((rec.on_disk or rec.path).stat().st_mtime) >= int(since)):
            return rec.path.name
    return None
