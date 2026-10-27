"""The delegation baseline: what was already dirty in the worktree before the worker started (round 6, F11b).

``delegate`` snapshots the tracked-modified and untracked paths of the
worktree it launches into; ``reconcile`` leaves those out, so a coordinator's
own uncommitted edits (the usual case in a shared checkout) are not charged
to the worker as a touch-zone breach. The record schema is closed, so the
snapshot is a sidecar beside the record: ``work/.workers/<id>.baseline.json``.
"""

from __future__ import annotations

import json
from pathlib import Path

from specy_road.git_subprocess import run
from specy_road.worker_state import record_path


def baseline_path(repo_root: Path, worker_id: str) -> Path:
    return record_path(repo_root, worker_id).with_suffix(".baseline.json")


def dirty_now(worktree: Path) -> list[str]:
    """Tracked-modified and untracked paths right now, from ``status -z`` (raw, so a leading space survives)."""
    r = run(["status", "--porcelain", "--untracked-files=all", "-z"], worktree)
    if not r.ok:
        return []
    out: set[str] = set()
    fields = iter(r.out.split("\0"))
    for entry in fields:
        if len(entry) < 4:
            continue
        out.add(entry[3:])
        if entry[0] in "RC":
            next(fields, None)   # a rename carries the old path as the next field
    return sorted(out)


def write_baseline(repo_root: Path, worker_id: str, worktree: Path) -> list[str]:
    paths = dirty_now(worktree)
    baseline_path(repo_root, worker_id).write_text(json.dumps({"dirty_paths": paths}), encoding="utf-8")
    return paths


def read_baseline(repo_root: Path, worker_id: str) -> list[str]:
    path = baseline_path(repo_root, worker_id)
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return []
    return [str(p) for p in (data.get("dirty_paths") or [])] if isinstance(data, dict) else []
