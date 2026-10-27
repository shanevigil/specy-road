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
from specy_road.git_subprocess import git_text
from specy_road.review_target import ReviewTargetError, resolve_target
from specy_road.worker_baseline import read_baseline
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
    out = git_text(["diff", "--name-only", since_sha], worktree) or ""
    untracked = git_text(["ls-files", "--others", "--exclude-standard"], worktree) or ""
    return sorted({p for p in (out + "\n" + untracked).splitlines() if p.strip()})


def _bookkeeping(path: str) -> bool:
    return path.startswith("work/") or path == "roadmap/registry.yaml"


def reconcile(repo_root: Path, worker_id: str) -> tuple[WorkerRecord, dict[str, Any]]:
    with workers_lock(repo_root):   # one reading of checkpoint, lease and flags
        return _reconcile_locked(repo_root, load_record(repo_root, worker_id))


def _reconcile_locked(repo_root: Path, rec: WorkerRecord) -> tuple[WorkerRecord, dict[str, Any]]:
    t = _target(repo_root, rec.node_id)
    since = (rec.checkpoint or {}).get("git_head") or t.base
    # Paths already dirty when `delegate` ran are the coordinator's, not the worker's.
    pre_existing = set(read_baseline(repo_root, rec.worker_id))
    changed = [p for p in _changed_since(Path(rec.worktree), since) if p not in pre_existing]
    zones = t.touch_zones
    # A breach is judged over the worker's whole lifetime, not only since the
    # last checkpoint: a hand-off moves the checkpoint past earlier commits,
    # and what they touched is still on the branch.
    origin = rec.started_head or since
    on_branch = ([p for p in _changed_since(Path(rec.worktree), origin) if p not in pre_existing]
                 if origin != since else changed)
    # Toolkit bookkeeping is never a breach: briefs, prompts, hand-off and
    # brainstorm files under work/, and the registry row the claim lives in.
    substantive = [p for p in sorted(set(changed) | set(on_branch)) if not _bookkeeping(p)]
    outside = [p for p in substantive if zones and not any(zone_matches(z, p) for z in zones)]
    text, _p, err = build_prompt(repo_root, rec.node_id, role="executor", model=rec.model)
    # A prompt that can no longer be built (the model lost the leaf's
    # sensitivity or class) is a contract change too, not a pass.
    contract_changed = bool(rec.contract_hash and (err or hashlib.sha256(text.encode("utf-8")).hexdigest() != rec.contract_hash))
    if outside or contract_changed:
        add_flag(repo_root, rec, FLAG_RECONCILE)
    else:
        clear_flag(repo_root, rec, FLAG_RECONCILE)
    delta = {"since": since, "changed": changed, "outside_touch_zones": outside,
             "contract_changed": contract_changed, "epoch": rec.instruction_epoch,
             "needs_reconcile": FLAG_RECONCILE in rec.flags, "pre_existing_dirty": sorted(pre_existing)}
    append_event(repo_root, rec, "reconcile", source="orchestrator", authority="orchestrator",
                 summary=(f"{len(changed)} path(s) changed, {len(outside)} outside touch zones"
                          + ("; contract changed" if contract_changed else "")), detail=delta)
    return rec, delta


# --- sync ------------------------------------------------------------------

def _sync_path(repo_root: Path) -> Path:
    return workers_dir(repo_root) / "sync.yaml"


def sync(repo_root: Path, *, ack: bool = False) -> list[dict[str, Any]]:
    """Per worker, the events after the last acknowledged one; ``ack`` moves the mark.

    Under the workers lock: dead wrappers are closed first so their ``error``
    is in this delta, and an acknowledgement only ever moves a mark forward,
    so two coordinators acking at once cannot push one back.
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
                        "events": [{"seq": e.seq, "type": e.type, "source": e.source, "summary": e.summary} for e in evs]})
            if ack:
                marks[rec.worker_id] = max(marks.get(rec.worker_id, 0), evs[-1].seq)
        if ack and out:
            path.parent.mkdir(parents=True, exist_ok=True)
            _write_atomic(path, yaml.safe_dump(marks, sort_keys=True))
    return out
