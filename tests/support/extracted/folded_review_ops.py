"""Helpers shared by tests that folded into more than one module."""

from __future__ import annotations

from pathlib import Path
from specy_road.orchestration.workers import worker_state as ws



def idle_record(
    repo: Path, node: str = "M1.1", harness: str = "claude-code", sid: str = "sid-1",
) -> ws.WorkerRecord:
    """An idle worker record bound to a provider session id."""
    rec = ws.create_record(repo, node, harness, "opus", repo, branch="feature/rm-thing")
    ws.mutate(repo, rec, lambda r: setattr(r, "provider_session_id", sid))
    ws.set_state(repo, rec, "idle", pid=None)
    return rec
