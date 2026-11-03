"""READY completion messaging for :mod:`worker_runner` (M11.27 — invalid vs missing)."""

from __future__ import annotations

import hashlib
from pathlib import Path

from specy_road.review_files import READY_PREFIX, _files
from specy_road.review_target import same_commit
from specy_road.worker_process import branch_mismatch, new_ready
from specy_road.worker_state import WorkerRecord, append_event


def ready_fingerprint(path: Path) -> str:
    return f"{path.name}:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def all_ready_fingerprints(repo_root: Path, node_id: str) -> list[str]:
    """Every READY path's content fingerprint, valid or not — the turn's full checkpoint."""
    return sorted(ready_fingerprint(p) for p in _files(repo_root, node_id, READY_PREFIX))


def fresh_invalid_ready_reason(repo_root: Path, rec: WorkerRecord, before_all: list[str]) -> str | None:
    """Why a new or changed READY this turn is unusable; same text handoff status shows."""
    from specy_road.bundled_scripts.brief_acceptance import acceptance_ids
    from specy_road.bundled_scripts.roadmap_load import load_roadmap
    from specy_road.review_files import list_ready

    node = next(n for n in load_roadmap(repo_root)["nodes"] if n.get("id") == rec.node_id)
    fresh = [
        r for r in list_ready(repo_root, rec.node_id, rec.branch, acceptance_ids(node))
        if not r.ok and ready_fingerprint(r.path) not in before_all
    ]
    if not fresh:
        return None
    pick = max(fresh, key=lambda r: (r.path.stat().st_mtime, r.path.name))
    return "; ".join(pick.errors)


def completion_summary(repo_root: Path, rec: WorkerRecord, before_all: list[str], ready: bool) -> str:
    if ready:
        return "exit 0; READY file present"
    invalid = fresh_invalid_ready_reason(repo_root, rec, before_all)
    if invalid:
        return f"exit 0; READY file invalid: {invalid}"
    return "exit 0; READY file missing"


def fresh_ready(repo_root: Path, rec: WorkerRecord, before: list[str]) -> bool:
    """A READY for this node that appeared or changed during this turn, on the branch actually checked out."""
    ready = new_ready(repo_root, rec.node_id, before)
    if ready is None or str(ready.data.get("node_id")) != rec.node_id:
        return False
    if rec.branch and str(ready.data.get("branch")) != rec.branch:
        return False
    why = branch_mismatch(Path(rec.worktree), rec.branch)
    if why:
        append_event(repo_root, rec, "error", source="system", summary=f"READY {ready.path.name} ignored: {why}")
        return False
    if not same_commit(Path(rec.worktree), str(ready.data.get("commit") or ""), "HEAD"):
        return False
    return True
