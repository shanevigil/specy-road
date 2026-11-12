"""One read of orchestration state: claims, workers, worktrees and reviews, per leaf.

:func:`read_state` reads every source once; :func:`snapshot` turns that into the schema-1 document
(``tests/fixtures/orchestration_snapshot_v1.json``). Nothing here writes: no record, registry,
review file or git index changes, and git runs with ``--no-optional-locks`` so ``status`` does not
refresh the index.

Each leaf's status comes from the fixture's truth table, first match wins. The abandoned rule is
M15.26's, stated once in :func:`specy_road.orphaned_claims.orphaned_claims`; the slot states are
:data:`specy_road.worker_orphans.SLOT_STATES`. An unreadable source sets only its own fields to
``unknown``: an unreadable worker record is listed with its id and nothing else, and every status is
judged from the readable records, as the M15.26 report judges them.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


from specy_road.chore_records import load_chore
from specy_road.git_subprocess import git_text, run
from specy_road.orchestration.claims import read_claims
from specy_road.orphaned_claims import orphaned_claims
from specy_road.review_files import list_reviews
from specy_road.review_target import same_commit
from specy_road.worker_orphans import SLOT_STATES
from specy_road.worker_process import wrapper_alive
from specy_road.worker_state import WorkerError, WorkerRecord, load_record, workers_dir

SCHEMA = 1
UNKNOWN = "unknown"
_ENDED = frozenset({"completed", "failed", "terminated"})


@dataclass
class OrchestrationState:
    """What :func:`read_state` read. ``claims`` is ``None`` when the registry cannot be read."""

    repo_root: Path
    records: list[WorkerRecord]
    unreadable_workers: list[str]
    claims: dict[str, dict[str, Any]] | None
    abandoned: list[dict[str, str]]
    worktrees: dict[str, str | None]  # resolved path -> branch, None when detached

    def active_records(self) -> list[WorkerRecord]:
        """The records ``worker list`` shows without ``--all``: not failed or terminated."""
        return [r for r in self.records if r.active]


def read_state(repo_root: Path) -> OrchestrationState:
    """Read worker records, registry claims, the M15.26 claim report and the git worktrees, once.

    The M15.26 report (:func:`orphaned_claims`) reads the registry itself, so it runs only when
    :func:`read_claims` found a readable registry: an unknown registry has no abandoned claims and
    never reaches that second read. Limit: a registry rewritten between the two reads is judged
    from both versions.
    """
    records, unreadable = _records(repo_root)
    claims = read_claims(repo_root)
    abandoned = orphaned_claims(repo_root) if claims is not None else []
    return OrchestrationState(
        repo_root, records, unreadable, claims, abandoned, _git_worktrees(repo_root)
    )


def snapshot(repo_root: Path) -> dict[str, Any]:
    """The schema-1 snapshot: ``schema``, ``leaves`` by node id, ``leafless_workers``. Read-only."""
    state = read_state(repo_root)
    leafless = [_worker(r) for r in state.records if load_chore(repo_root, r.node_id) is not None]
    leafless += [_unreadable_worker(wid) for wid in state.unreadable_workers]
    return {
        "schema": SCHEMA,
        "leaves": {nid: _leaf(state, nid) for nid in _leaf_ids(state)},
        "leafless_workers": leafless,
    }


def leaf_status(state: OrchestrationState, node_id: str) -> str:
    """The truth table's status for ``node_id`` (tests/fixtures/orchestration_snapshot_v1.json)."""
    mine = [r for r in state.records if r.node_id == node_id]
    if any(r.state in SLOT_STATES for r in mine):
        return "running"
    if state.claims is None:
        return UNKNOWN
    if any(c["node_id"] == node_id for c in state.abandoned):
        return "abandoned"
    if mine:
        latest = max(mine, key=lambda r: (r.attempt, r.worker_id))
        if latest.state == "completed":
            return "exited_ok"
        if latest.state in _ENDED:
            return "exited_failed"
    return "claimed"


def _records(repo_root: Path) -> tuple[list[WorkerRecord], list[str]]:
    """Every readable worker record, and the ids of those that cannot be read.

    ``list_records`` skips an unreadable record; the snapshot lists it under ``leafless_workers``.
    """
    d = workers_dir(repo_root)
    readable, unreadable = [], []
    for p in sorted(d.glob("w-*.yaml")) if d.is_dir() else []:
        try:
            readable.append(load_record(repo_root, p.stem))
        except WorkerError:
            unreadable.append(p.stem)
    return readable, unreadable


def _git_worktrees(repo_root: Path) -> dict[str, str | None]:
    """Resolved worktree path -> its branch's short name, or ``None`` when detached."""
    out: dict[str, str | None] = {}
    for block in (git_text(["worktree", "list", "--porcelain"], repo_root) or "").split("\n\n"):
        wt = dict(line.partition(" ")[::2] for line in block.splitlines())
        if "worktree" in wt:
            out[str(Path(wt["worktree"]).resolve())] = (
                wt.get("branch", "").removeprefix("refs/heads/") or None
            )
    return out


def _leaf_ids(state: OrchestrationState) -> list[str]:
    ids = set(state.claims or {})
    ids |= {r.node_id for r in state.records if load_chore(state.repo_root, r.node_id) is None}
    return sorted(ids)


def _leaf(state: OrchestrationState, node_id: str) -> dict[str, Any]:
    entry = None if state.claims is None else state.claims.get(node_id)
    branch = str(entry["branch"]) if entry and entry.get("branch") else None
    mine = [r for r in state.records if r.node_id == node_id]
    return {
        "claim": UNKNOWN
        if state.claims is None
        else None
        if entry is None
        else {
            "codename": str(entry.get("codename") or ""),
            "branch": branch,
            "registered_at": str(entry["started"]) if entry.get("started") else None,
        },
        "workers": [_worker(r) for r in mine],
        "worktrees": _worktrees(state, branch, mine),
        "reviews": _reviews(state.repo_root, node_id, branch),
        "status": leaf_status(state, node_id),
    }


def _worker(rec: WorkerRecord) -> dict[str, Any]:
    return {
        "id": rec.worker_id,
        "harness": rec.harness,
        "model": rec.model,
        "status": rec.state,
        "pid_alive": wrapper_alive(rec),
        "started_at": rec.created,
        "ended_at": rec.updated if rec.state in _ENDED else None,
    }


def _unreadable_worker(worker_id: str) -> dict[str, Any]:
    return {
        "id": worker_id,
        **dict.fromkeys(
            ("harness", "model", "status", "pid_alive", "started_at", "ended_at"), UNKNOWN
        ),
    }


def _worktrees(
    state: OrchestrationState, branch: str | None, mine: list[WorkerRecord]
) -> list[dict[str, Any]]:
    paths = {p for p, b in state.worktrees.items() if branch and b == branch}
    paths |= {str(Path(r.worktree).resolve()) for r in mine}
    return [
        {"path": p, "branch": state.worktrees.get(p), "dirty": _dirty(Path(p))}
        for p in sorted(paths)
    ]


def _dirty(path: Path) -> bool | str:
    """Whether git status lists anything; ``unknown`` when git cannot read ``path``.

    ``--no-optional-locks``: a read must not refresh and rewrite the index.
    """
    if not path.is_dir():
        return UNKNOWN
    r = run(["--no-optional-locks", "status", "--porcelain", "--untracked-files=all"], path)
    return bool(r.out.strip()) if r.ok else UNKNOWN


def _reviews(repo_root: Path, node_id: str, branch: str | None) -> list[dict[str, Any]]:
    tip = (
        git_text(["rev-parse", "--verify", "--quiet", f"{branch}^{{commit}}"], repo_root)
        if branch
        else None
    )
    out = []
    for review in list_reviews(repo_root, node_id):
        commit = review.data.get("commit")
        out.append(
            {
                "model": review.data.get("model") or UNKNOWN,
                "verdict": review.data.get("verdict") or UNKNOWN,
                "commit": commit or UNKNOWN,
                "fresh_for_head": same_commit(repo_root, str(commit), tip)
                if commit and tip
                else UNKNOWN,
            }
        )
    return out
