"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

from specy_road.orchestration.grind.session_plan import SessionPlan
from specy_road.orchestration.grind.session_plan import Wave

def plan(ready=None, blocked=None, active=None):
    """Shared test helper."""
    ready = ready or []
    return SessionPlan(
        under=None,
        ready=list(ready),
        blocked=list(blocked or []),
        active=list(active or []),
        closed=[],
        gated=[],
        gates_open=[],
        needs_codename=[],
        waves=[Wave(index=0, node_ids=list(ready))] if ready else [],
        parallel_batches=[list(ready)] if ready else [],
        totals={"ready": len(ready)},
    )
