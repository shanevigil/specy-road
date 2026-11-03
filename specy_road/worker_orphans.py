"""Held workers whose leaf is over: they free their ``max_workers`` slot and show as orphaned (M11.57).

An ``idle`` or ``completed`` worker keeps its leaf and its slot, so a review ``block`` can resume it for a
fix round. Once its leaf is over, no fix round can come: it no longer counts against ``policy.max_workers``,
``worker list`` / ``sync`` show it orphaned, and ``worker terminate --orphaned`` ends it. ``finish-this-task``
ends the finished leaf's own idle and completed workers.

One conservative rule decides "over", for the slot count, the orphan marks and the bulk terminate alike: at
**every** integration ref that exists (the local integration branch and its remote-tracking ref), the leaf has
no registry claim **and** the leaf is Complete in that same ref's roadmap. Pickup registers claims there and
finish removes them and marks the leaf Complete there, so both move together when a leaf lands. Anything
less keeps the worker: no such ref, a registry or graph that cannot be read, a leaf missing from a graph,
refs that disagree (a stale ``origin/<branch>`` still saying Complete for a leaf reopened since, or a local
landing not yet pushed), or a claim on the leaf under any branch. The caller's working tree is never read:
linked worktrees share the records, and an older lane's snapshot is no authority. A worker whose worktree is
gone is orphaned under the same rule only; the reason then says so too.

Nothing here is stored: the record and event schemas name no such flag, and a leaf can be reopened or
claimed again, so it is judged afresh on every read.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Iterable
from functools import cached_property
from pathlib import Path
from typing import Any

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

    def over(self, node_id: str) -> str | None:
        """The refs' labels when every one of them shows ``node_id`` unclaimed and Complete; ``None`` otherwise."""
        if not self.views:
            return None
        for _label, claimed, status in self.views:
            if claimed is None or status is None or node_id in claimed or status.get(node_id) != "complete":
                return None
        return " and ".join(label for label, _c, _s in self.views)


def _cause(rec: WorkerRecord, leaves: _Leaves) -> str | None:
    """Why a held worker is orphaned (and frees its slot), else ``None``: its leaf is over by :meth:`_Leaves.over`."""
    if rec.state not in HELD_STATES or not (where := leaves.over(rec.node_id)):
        return None
    why = f"{rec.node_id} is Complete and unclaimed on {where}"
    return why if Path(rec.worktree).is_dir() else f"{why}; worktree {rec.worktree} is gone"


def holding_slots(repo_root: Path, records: Iterable[WorkerRecord]) -> list[WorkerRecord]:
    """The active ``records`` that count toward ``policy.max_workers``: all but held workers whose leaf is over."""
    leaves = _Leaves(repo_root)
    return [r for r in records if r.active and not _cause(r, leaves)]


def orphans(repo_root: Path, records: Iterable[WorkerRecord] | None = None) -> dict[str, str]:
    """Worker id -> why, for each held worker whose leaf is over (unclaimed and Complete at every integration ref)."""
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
