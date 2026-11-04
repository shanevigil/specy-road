"""Held workers whose leaf is over: they free their ``max_workers`` slot and show as orphaned (M11.57).

An ``idle`` or ``completed`` worker keeps its leaf and its slot, so a review ``block`` can resume it for a
fix round. Once its leaf is over, no fix round can come: it no longer counts against ``policy.max_workers``,
``worker list`` / ``sync`` show it orphaned, and ``worker terminate --orphaned`` ends it. ``finish-this-task``
ends the finished leaf's own idle and completed workers.

Three causes decide "over", each on its own, for the slot count, the orphan marks and the bulk terminate
alike (review round 3: the round-2 rule needed claim-gone AND Complete together, which dropped two of the
criteria's causes):

- **unclaimed**: at every integration ref that exists (the local integration branch and its remote-tracking
  ref), the registry is readable and has no claim on the leaf under any branch, whatever the leaf's status
  (a landed finish, ``registry-prune --remove``, an abandoned leaf);
- **Complete**: at every such ref, the roadmap is readable and says the leaf is Complete;
- **worktree gone**: the record's worktree is no longer a directory (local state, not a ref snapshot).

The two ref causes need every existing ref to agree, so a stale snapshot can only keep a worker, never free
one: a stale ``origin/<branch>`` still saying Complete or unclaimed for a leaf reopened and claimed since, or a
local landing not yet pushed and fetched, keeps it. With no such ref, or one whose registry (graph) cannot be
read, the unclaimed (Complete) cause is not judged at all. The caller's working tree is never read: linked
worktrees share the records, and an older lane's registry snapshot is no authority.

Nothing here is stored: the record and event schemas name no such flag, and a leaf can be reopened or
claimed again, so it is judged afresh on every read.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Iterable
from functools import cached_property
from pathlib import Path
from typing import Any

from specy_road.bundled_scripts.chore_cli import load_chore
from specy_road.bundled_scripts.roadmap_load_at_ref import load_roadmap_nodes_at_ref
from specy_road.git_subprocess import git_text
from specy_road.git_workflow_config import resolve_integration_defaults
from specy_road.registry_remote_overlay_merge import read_registry_at_ref
from specy_road.runtime_paths import add_repo_root_arg, resolve_repo_root
from specy_road.worker_state import WorkerRecord, list_records, workers_lock

#: Not running, still owning the leaf: what a leaf that is over releases.
HELD_STATES = frozenset({"idle", "completed"})
RUNNING_STATES = frozenset({"starting", "running"})
_HINT = "(`specy-road worker terminate --orphaned` ends them)"
_REF_TIMEOUT = 30.0   # one ``git show`` of a registry blob, as finish reads one


class _Leaves:
    """What held workers are judged against; each ref is read at most once per call, and only when asked."""

    def __init__(self, repo_root: Path) -> None:
        self.root = repo_root

    @cached_property
    def refs(self) -> list[tuple[str, str]]:
        """``(full ref, label)`` for the integration branch's local branch and remote-tracking ref, those that exist."""
        base, remote, _warnings = resolve_integration_defaults(self.root, explicit_base=None, explicit_remote=None)
        both = ((f"refs/heads/{base}", base), (f"refs/remotes/{remote}/{base}", f"{remote}/{base}"))
        return [(full, label) for full, label in both
                if git_text(["rev-parse", "--verify", "--quiet", full], self.root)]

    @cached_property
    def views(self) -> list[tuple[str, set[str] | None, dict[str, str] | None]]:
        """Per ref in :attr:`refs`: ``(label, claimed node ids, node id -> status)``; ``None`` where unreadable."""
        out = []
        for full, label in self.refs:
            reg = read_registry_at_ref(self.root, full, _REF_TIMEOUT)
            nodes = load_roadmap_nodes_at_ref(self.root, full)
            claimed = None if reg is None else {str(e.get("node_id")) for e in (reg.get("entries") or [])
                                                if isinstance(e, dict)}
            status = None if nodes is None else {str(n.get("id")): str(n.get("status") or "").lower() for n in nodes}
            out.append((label, claimed, status))
        return out

    def _agreed(self, holds: Callable[[set[str] | None, dict[str, str] | None], bool]) -> str | None:
        """The refs' labels when there is a ref and every one agrees by ``holds(claimed, status)``; else ``None``."""
        if not self.views or not all(holds(claimed, status) for _label, claimed, status in self.views):
            return None
        return " and ".join(label for label, _c, _s in self.views)

    def unclaimed(self, node_id: str) -> str | None:
        """Where ``node_id`` has no claim: every ref, each with a readable registry; else ``None``."""
        return self._agreed(lambda claimed, _status: claimed is not None and node_id not in claimed)

    def complete(self, node_id: str) -> str | None:
        """Where ``node_id`` is Complete: every ref, each with a readable graph; else ``None``."""
        return self._agreed(lambda _claimed, status: status is not None and status.get(node_id) == "complete")


def _cause(rec: WorkerRecord, leaves: _Leaves) -> str | None:
    """Why a held worker is orphaned (and frees its slot), else ``None``: each cause found, ``; ``-joined."""
    if rec.state not in HELD_STATES:
        return None
    why = []
    chore = load_chore(leaves.root, rec.node_id)   # no claim or graph node: a chore is over once it is closed
    if chore is not None and chore.get("closed_at"):
        why.append(f"chore {rec.node_id} is closed")
    # Only a record that names the claim it was delegated under can have lost it (delegate and adopt always
    # set ``branch``); one without never had a claim to compare, so the claim cause does not apply to it.
    if chore is None and rec.branch and (where := leaves.unclaimed(rec.node_id)):
        why.append(f"no claim on {rec.node_id} on {where}")
    if chore is None and (where := leaves.complete(rec.node_id)):
        why.append(f"{rec.node_id} is Complete on {where}")
    if not Path(rec.worktree).is_dir():
        why.append(f"worktree {rec.worktree} is gone")
    return "; ".join(why) or None


def holding_slots(repo_root: Path, records: Iterable[WorkerRecord]) -> list[WorkerRecord]:
    """The active ``records`` that count toward ``policy.max_workers``: all but held workers whose leaf is over."""
    leaves = _Leaves(repo_root)
    return [r for r in records if r.active and not _cause(r, leaves)]


def orphans(repo_root: Path, records: Iterable[WorkerRecord] | None = None) -> dict[str, str]:
    """Worker id -> why, for each held worker whose leaf is over: unclaimed or Complete at every integration ref,
    or its worktree gone."""
    leaves = _Leaves(repo_root)
    recs = list_records(repo_root, active_only=True) if records is None else records
    return {r.worker_id: why for r in recs if (why := _cause(r, leaves))}


def slot_breakdown(held: list[WorkerRecord]) -> str:
    """``2 running: w-0002, w-0003; 1 completed: w-0001`` and what frees a slot, for the ``max_workers`` refusal."""
    groups: dict[str, list[str]] = {}
    for r in held:
        groups.setdefault("running" if r.state in RUNNING_STATES else r.state, []).append(r.worker_id)
    parts = [f"{len(ids)} {state}: {', '.join(ids)}" for state, ids in sorted(groups.items(), key=lambda kv: kv[0] != "running")]
    idle = [r.worker_id for r in held if r.state in HELD_STATES]
    if not idle:
        return "; ".join([*parts, "wait for one to finish or raise the limit"])
    which = idle[0] if len(idle) == 1 else "<id>"
    return "; ".join(parts) + (f"; `specy-road worker terminate {which}` frees {'it' if len(idle) == 1 else 'one'}, "
                               "or wait for a running one to finish or raise the limit")


def _end(repo_root: Path, pick: Callable[[WorkerRecord], str | None]) -> list[tuple[WorkerRecord, str]]:
    """Terminate every active worker ``pick`` names a reason for, under one lock; one lease release after it."""
    if not any(pick(r) for r in list_records(repo_root, active_only=True)):
        return []   # read before locking: the lock would create work/.workers/ in a checkout that has no workers
    with workers_lock(repo_root):
        found = [(r, why) for r in list_records(repo_root, active_only=True) if (why := pick(r))]
        if not found:
            return []
        from specy_road.worker_ops import _terminate_locked   # noqa: PLC0415 — ops imports this module
        ended = [(_terminate_locked(repo_root, r), why) for r, why in found]
    from specy_road.worker_lease import release_lease   # noqa: PLC0415 — worker_lease imports this module
    release_lease(repo_root, *(r.worker_id for r, _why in ended))   # a network call: after the lock
    return ended


def terminate_orphaned(repo_root: Path) -> list[tuple[WorkerRecord, str]]:
    """``worker terminate --orphaned``: end every held worker :func:`orphans` names, with its reason."""
    leaves = _Leaves(repo_root)
    return _end(repo_root, lambda r: _cause(r, leaves))


def end_finished_workers(repo_root: Path, node_id: str) -> list[tuple[WorkerRecord, str]]:
    """``finish-this-task``: end ``node_id``'s idle and completed workers (a running one is left alone)."""
    return _end(repo_root, lambda r: r.node_id == node_id and r.state in HELD_STATES
                and f"{node_id} finished while {r.worker_id} was {r.state}")


# --- CLI glue: worker_cli.py sits at the line cap ---------------------------------------------------------------

def orphan_lines(gone: dict[str, str]) -> list[str]:
    if not gone:
        return []
    return [*(f"orphaned: {w} ({why})" for w, why in gone.items()), _HINT]


def with_orphans(repo_root: Path, data: dict[str, Any], lines: list[str]) -> tuple[dict[str, Any], list[str]]:
    """``worker sync``'s JSON and lines with every orphaned worker added, whether or not it wrote an event."""
    gone = orphans(repo_root)
    return {**data, "orphaned": gone}, lines + orphan_lines(gone)


def list_view(repo_root: Path, recs: list[WorkerRecord], row: Callable[[WorkerRecord], dict[str, Any]],
              line: Callable[..., str]) -> tuple[dict[str, Any], list[str]]:
    """``worker list``'s JSON and lines, each held worker whose leaf is over marked ``orphaned`` with its reason."""
    gone = orphans(repo_root, recs)
    rows = [{**row(r), "orphaned": gone.get(r.worker_id)} for r in recs]
    lines = [line(r, repo_root) + (f"  orphaned: {gone[r.worker_id]}" if r.worker_id in gone else "") for r in recs]
    return {"workers": rows}, lines + ([_HINT] if gone else [])


def add_terminate(ws: Any, one: Callable[[argparse.Namespace], int],
                  emit: Callable[[argparse.Namespace, dict[str, Any], list[str]], int]) -> None:
    """``worker terminate W`` (``one``) or ``worker terminate --orphaned``, which ends them all and prints each."""
    sp = ws.add_parser("terminate", help="SIGTERM the worker and close its record (--orphaned: every orphaned one)")
    sp.add_argument("worker_id", metavar="W", nargs="?")
    sp.add_argument("--orphaned", action="store_true", help="Every idle/completed worker whose leaf is over")
    sp.add_argument("--json", action="store_true")
    sp.add_argument("--op-id", metavar="ID", help="Idempotency key; a retry returns the first result (one W only)")
    add_repo_root_arg(sp)

    def run(ns: argparse.Namespace) -> int:
        if bool(ns.worker_id) == ns.orphaned or (ns.orphaned and ns.op_id):
            sp.error("give one worker id, or --orphaned (without --op-id)")
        if not ns.orphaned:
            return one(ns)
        ended = terminate_orphaned(resolve_repo_root(ns))
        return emit(ns, {"terminated": [{"worker_id": r.worker_id, "node_id": r.node_id, "why": why} for r, why in ended]},
                    [f"{r.worker_id}: terminated ({why})" for r, why in ended] or ["No orphaned workers."])

    sp.set_defaults(func=run)
