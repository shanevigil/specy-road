"""``worker reconcile`` and ``worker sync``: what changed since the checkpoint, and the unread events (slice 7c).

Split from :mod:`specy_road.worker_ops` for the file limit; the CLI reaches
them through that module.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import yaml

from specy_road.bundled_scripts.generate_brief import index, render_brief
from specy_road.bundled_scripts.role_prompt import build_prompt
from specy_road.finish_implementation_check import _clean, zone_matches
from specy_road.git_changed_paths import diff_paths
from specy_road.git_subprocess import git_text
from specy_road.review_target import ReviewTargetError, resolve_target
from specy_road.runtime_paths import git_root, project_prefix, rebase_to_project
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
    # Named from the git root over the whole repo, as `git diff` names them: the
    # worktree may be a nested project root, where plain ls-files is directory-relative.
    untracked = git_text(["ls-files", "--others", "--exclude-standard", "--full-name", "--", ":(top)"], worktree) or ""
    return sorted(set(changed) | {p for p in untracked.splitlines() if p.strip()})


#: specy-road's state under work/: gitignored by the project template, listed by git where it is not.
_STATE_DIRS = ("work/reviews/", "work/.workers/", "work/.sessions/", "work/.worktrees/")


def _delegated_brief(repo_root: Path, rec: WorkerRecord) -> Path:
    wt = Path(rec.worktree)
    return git_root(wt) / project_prefix(repo_root) / "work" / f"brief-{rec.node_id}.md"


def _brief_unchanged(repo_root: Path, rec: WorkerRecord, nodes: list[dict]) -> bool:
    """A fresh brief render matches the copy the worker was given in its worktree."""
    brief = _delegated_brief(repo_root, rec)
    if not brief.is_file():
        return False
    fresh = render_brief(rec.node_id, index(nodes), repo_root=repo_root, include_history=False)
    return fresh == brief.read_text(encoding="utf-8")


def _bookkeeping(path: str, node_id: str, prefix: str = "") -> bool:
    """The leaf's own specy-road files: the brief and summary the reviewer's clean-tree check leaves
    out (role_prompt), the prompts ``delegate`` writes, and the toolkit's state.

    ``path`` is git-root-relative; ``prefix`` is the project's (nested layout). A path outside the
    project, such as the git root's own ``work/``, is never the leaf's bookkeeping.
    """
    rel = rebase_to_project(path, prefix)
    return rel is not None and (rel in (f"work/brief-{node_id}.md", f"work/implementation-summary-{node_id}.md")
                                or rel.startswith((f"work/prompt-{node_id}-", *_STATE_DIRS)))


def reconcile(repo_root: Path, worker_id: str) -> tuple[WorkerRecord, dict[str, Any]]:
    with workers_lock(repo_root):   # one reading of checkpoint, lease and flags
        return _reconcile_locked(repo_root, load_record(repo_root, worker_id))


def _reconcile_locked(repo_root: Path, rec: WorkerRecord) -> tuple[WorkerRecord, dict[str, Any]]:
    t = _target(repo_root, rec.node_id)
    since = (rec.checkpoint or {}).get("git_head") or t.base
    changed = _changed_since(Path(rec.worktree), since)
    zones = [z for z in (_clean(z) for z in t.touch_zones) if z]
    # A breach is judged over the worker's whole lifetime, not only since the
    # last checkpoint: a hand-off moves the checkpoint past earlier commits,
    # and what they touched is still on the branch.
    origin = rec.started_head or since
    on_branch = _changed_since(Path(rec.worktree), origin) if origin != since else changed
    # Toolkit bookkeeping is never a breach: the leaf's brief, summary and
    # review files, and the registry row the claim lives in. Paths are named
    # from the git root; zones are matched as the review packet matches them,
    # by the project-relative name inside the project, the git-root name outside.
    prefix = project_prefix(repo_root)
    substantive = [p for p in sorted(set(changed) | set(on_branch))
                   if not (_bookkeeping(p, rec.node_id, prefix) or rebase_to_project(p, prefix) == "roadmap/registry.yaml")]
    outside = [p for p in substantive
               if zones and not any(zone_matches(z, rebase_to_project(p, prefix) or p) for z in zones)]
    text, _p, err = build_prompt(repo_root, rec.node_id, role="executor", model=rec.model)
    # A prompt that can no longer be built (the model lost the leaf's
    # sensitivity or class) is a contract change too, not a pass.
    brief_same = _brief_unchanged(repo_root, rec, t.nodes)
    prompt_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    contract_changed = bool(
        rec.contract_hash
        and (err or (prompt_hash != rec.contract_hash and not brief_same))
    )
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


def _gaps(after: int, seqs: list[int], last: int) -> list[list[int]]:
    """``[first, last]`` per run of sequence numbers in ``after+1 .. last`` that no readable event carries."""
    seen, out = set(seqs), []
    for seq in range(after + 1, last + 1):
        if seq in seen:
            continue
        if out and out[-1][1] == seq - 1:
            out[-1][1] = seq
        else:
            out.append([seq, seq])
    return out


def sync(repo_root: Path, *, ack: bool = False) -> list[dict[str, Any]]:
    """Per worker, the events after the last acknowledged one; ``ack`` moves the mark.

    Under the workers lock: dead wrappers are closed first so their ``error``
    is in this delta, and an acknowledgement only ever moves a mark forward,
    so two coordinators acking at once cannot push one back. ``gaps`` lists the
    sequence numbers between the mark and the record's ``last_event_seq`` that
    no readable line carries (lost or unreadable, the final one included); a
    worker with only gaps is listed too, and ``ack`` moves its mark past them.
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
            mark = marks.get(rec.worker_id, 0)
            evs = events_since(repo_root, rec.worker_id, mark)
            # append_event writes the line before it saves the record, so the
            # record's last_event_seq is a sequence that was logged.
            last = max([rec.last_event_seq, *(e.seq for e in evs)])
            if last <= mark:
                continue
            out.append({"worker_id": rec.worker_id, "node_id": rec.node_id, "state": rec.state,
                        "lease": rec.lease.get("holder"), "flags": list(rec.flags), "epoch": rec.instruction_epoch,
                        "gaps": _gaps(mark, [e.seq for e in evs], last),
                        "events": [{"seq": e.seq, "type": e.type, "source": e.source, "summary": e.summary,
                                    "detail": e.detail} for e in evs]})
            if ack:
                marks[rec.worker_id] = last
        if ack and out:
            path.parent.mkdir(parents=True, exist_ok=True)
            _write_atomic(path, yaml.safe_dump(marks, sort_keys=True))
    return out
