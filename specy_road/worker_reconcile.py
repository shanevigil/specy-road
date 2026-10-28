"""``worker reconcile`` and ``worker sync``: what changed since the checkpoint, and the unread events (slice 7c).

Split from :mod:`specy_road.worker_ops` for the file limit; the CLI reaches
them through that module.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import yaml

from specy_road.bundled_scripts.role_prompt import build_prompt
from specy_road.finish_implementation_check import zone_matches
from specy_road.git_changed_paths import diff_paths
from specy_road.git_subprocess import git_text
from specy_road.review_target import ReviewTargetError, resolve_target
from specy_road.runtime_paths import project_prefix, rebase_to_project
from specy_road.worker_process import branch_mismatch
from specy_road.worker_state import (
    FLAG_RECONCILE,
    WorkerError,
    WorkerRecord,
    _write_atomic,
    add_flag,
    append_event,
    clear_flag,
    events_since,
    list_records,
    load_record,
    workers_dir,
    workers_lock,
)


def _target(repo_root: Path, node_id: str):
    try:
        t = resolve_target(repo_root, node_id)
    except ReviewTargetError as e:
        raise WorkerError(str(e)) from None
    return t


def _changed_since(worktree: Path, since_sha: str | None) -> list[str]:
    if not since_sha:
        return []
    # Both sides of a rename or copy: a `git mv` into the zone is also a
    # deletion outside it.
    changed = diff_paths(worktree, since_sha) or []
    untracked = git_text(["ls-files", "--others", "--exclude-standard"], worktree) or ""
    return sorted(set(changed) | {p for p in untracked.splitlines() if p.strip()})


#: specy-road's state under work/: gitignored by the project template, listed by git where it is not.
_STATE_DIRS = ("work/reviews/", "work/.workers/", "work/.sessions/", "work/.worktrees/")


def _bookkeeping(path: str, node_id: str, prefix: str = "") -> bool:
    """The leaf's own specy-road files: the brief and summary the reviewer's clean-tree check leaves
    out (role_prompt), the prompts ``delegate`` writes, and the toolkit's state.

    ``prefix`` is the project's (nested layout): git names a path from the git root, ``ls-files``
    from the directory it runs in, so a path under the prefix is read without it.
    """
    path = rebase_to_project(path, prefix) or path
    return (path in (f"work/brief-{node_id}.md", f"work/implementation-summary-{node_id}.md")
            or path.startswith((f"work/prompt-{node_id}-", *_STATE_DIRS)))


def reconcile(repo_root: Path, worker_id: str) -> tuple[WorkerRecord, dict[str, Any]]:
    with workers_lock(repo_root):   # one reading of checkpoint, lease and flags
        return _reconcile_locked(repo_root, load_record(repo_root, worker_id))


def _reconcile_locked(repo_root: Path, rec: WorkerRecord) -> tuple[WorkerRecord, dict[str, Any]]:
    t = _target(repo_root, rec.node_id)
    since = (rec.checkpoint or {}).get("git_head") or t.base
    changed = _changed_since(Path(rec.worktree), since)
    zones = t.touch_zones
    # A breach is judged over the worker's whole lifetime, not only since the
    # last checkpoint: a hand-off moves the checkpoint past earlier commits,
    # and what they touched is still on the branch.
    origin = rec.started_head or since
    on_branch = _changed_since(Path(rec.worktree), origin) if origin != since else changed
    # Toolkit bookkeeping is never a breach: the leaf's brief, summary and
    # review files, and the registry row the claim lives in.
    prefix = project_prefix(repo_root)
    substantive = [p for p in sorted(set(changed) | set(on_branch))
                   if not (_bookkeeping(p, rec.node_id, prefix) or p == "roadmap/registry.yaml")]
    outside = [p for p in substantive if zones and not any(zone_matches(z, p) for z in zones)]
    text, _p, err = build_prompt(repo_root, rec.node_id, role="executor", model=rec.model)
    # A prompt that can no longer be built (the model lost the leaf's
    # sensitivity or class) is a contract change too, not a pass.
    contract_changed = bool(rec.contract_hash and (err or hashlib.sha256(text.encode("utf-8")).hexdigest() != rec.contract_hash))
    off_branch = branch_mismatch(Path(rec.worktree), rec.branch)   # the tree moved off the worker's branch (B12)
    if outside or contract_changed or off_branch:
        add_flag(repo_root, rec, FLAG_RECONCILE)
    else:
        clear_flag(repo_root, rec, FLAG_RECONCILE)
    delta = {"since": since, "changed": changed, "outside_touch_zones": outside,
             "contract_changed": contract_changed, "branch_mismatch": off_branch, "epoch": rec.instruction_epoch,
             "needs_reconcile": FLAG_RECONCILE in rec.flags}
    append_event(repo_root, rec, "reconcile", source="orchestrator", authority="orchestrator",
                 summary=(f"{len(changed)} path(s) changed, {len(outside)} outside touch zones"
                          + ("; contract changed" if contract_changed else "") + (f"; {off_branch}" if off_branch else "")),
                 detail=delta)
    return rec, delta


# --- sync ------------------------------------------------------------------

def _sync_path(repo_root: Path) -> Path:
    return workers_dir(repo_root) / "sync.yaml"


def _gaps(after: int, seqs: list[int]) -> list[list[int]]:
    """``[first, last]`` per run of sequence numbers missing between the mark ``after`` and the events read."""
    out, expect = [], after + 1
    for seq in seqs:
        if seq > expect:
            out.append([expect, seq - 1])
        expect = max(expect, seq + 1)
    return out


def sync(repo_root: Path, *, ack: bool = False) -> list[dict[str, Any]]:
    """Per worker, the events after the last acknowledged one; ``ack`` moves the mark.

    Under the workers lock: dead wrappers are closed first so their ``error``
    is in this delta, and an acknowledgement only ever moves a mark forward,
    so two coordinators acking at once cannot push one back. ``gaps`` lists the
    sequence numbers missing before an event read (a lost or unreadable line).
    """
    from specy_road.worker_ops import sweep_dead_wrappers   # noqa: PLC0415 — ops imports this module

    path = _sync_path(repo_root)
    with workers_lock(repo_root):
        sweep_dead_wrappers(repo_root)
        marks: dict[str, int] = {}
        if path.is_file():
            marks = {str(k): int(v) for k, v in (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).items()}
        out = []
        for rec in list_records(repo_root):
            evs = events_since(repo_root, rec.worker_id, marks.get(rec.worker_id, 0))
            if not evs:
                continue
            out.append({"worker_id": rec.worker_id, "node_id": rec.node_id, "state": rec.state,
                        "lease": rec.lease.get("holder"), "flags": list(rec.flags), "epoch": rec.instruction_epoch,
                        "gaps": _gaps(marks.get(rec.worker_id, 0), [e.seq for e in evs]),
                        "events": [{"seq": e.seq, "type": e.type, "source": e.source, "summary": e.summary} for e in evs]})
            if ack:
                marks[rec.worker_id] = max(marks.get(rec.worker_id, 0), evs[-1].seq)
        if ack and out:
            path.parent.mkdir(parents=True, exist_ok=True)
            _write_atomic(path, yaml.safe_dump(marks, sort_keys=True))
    return out
