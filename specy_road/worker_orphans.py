"""Held workers whose leaf is over: they free their ``max_workers`` slot and show as orphaned (M11.57).

An ``idle`` or ``completed`` worker keeps its leaf and its slot, so a review ``block`` can resume it for a
fix round. Once its leaf is Complete on the integration branch, or the claim it was delegated under is gone
from this checkout's registry, no fix round can come: it no longer counts against ``policy.max_workers``,
and ``worker list`` / ``sync`` show it orphaned. So does one whose worktree no longer exists; that one keeps
its slot, since its leaf is still open. ``worker terminate --orphaned`` ends them all, and
``finish-this-task`` ends the finished leaf's own idle and completed workers.

Nothing here is stored: the record and event schemas name no such flag, and a cause can come and go
(a leaf reopened, a claim taken again), so it is judged afresh on every read.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Iterable
from functools import cached_property
from pathlib import Path
from typing import Any

import yaml

from specy_road.bundled_scripts.roadmap_load_at_ref import load_roadmap_nodes_at_ref
from specy_road.git_subprocess import git_text
from specy_road.git_workflow_config import resolve_integration_defaults
from specy_road.registry_yaml import read_registry, registry_path
from specy_road.runtime_paths import add_repo_root_arg, resolve_repo_root
from specy_road.worker_state import WorkerRecord, list_records, workers_lock

#: Not running, still owning the leaf: what a finished leaf or a lost claim releases.
HELD_STATES = frozenset({"idle", "completed"})
RUNNING_STATES = frozenset({"starting", "running"})
_HINT = "(`specy-road worker terminate --orphaned` ends them)"


class _Leaves:
    """What held workers are judged against; each is read at most once per call, and only when asked."""

    def __init__(self, repo_root: Path) -> None:
        self.root = repo_root

    @cached_property
    def claims(self) -> set[tuple[str, str]] | None:
        """``(node_id, branch)`` per registry claim; ``None`` when the registry cannot be read (nothing is gone)."""
        try:
            doc = read_registry(registry_path(self.root), missing_ok=False)
        except (OSError, ValueError, yaml.YAMLError):
            return None
        return {(str(e.get("node_id")), str(e.get("branch"))) for e in (doc.get("entries") or [])
                if isinstance(e, dict)}

    @cached_property
    def complete(self) -> dict[str, str]:
        """Node id -> the integration ref (local branch, else remote-tracking) whose graph says Complete."""
        base, remote, _warnings = resolve_integration_defaults(self.root, explicit_base=None, explicit_remote=None)
        out: dict[str, str] = {}
        for full, label in ((f"refs/heads/{base}", base), (f"refs/remotes/{remote}/{base}", f"{remote}/{base}")):
            if not git_text(["rev-parse", "--verify", "--quiet", full], self.root):
                continue
            for n in load_roadmap_nodes_at_ref(self.root, full) or []:
                if str(n.get("status") or "").lower() == "complete":
                    out.setdefault(str(n.get("id")), label)
        return out


def _cause(rec: WorkerRecord, leaves: _Leaves) -> tuple[bool, str] | None:
    """``(frees_its_slot, why)`` for a held worker whose leaf is over or whose worktree is gone, else ``None``."""
    if rec.state not in HELD_STATES:
        return None
    if rec.branch and leaves.claims is not None and (rec.node_id, rec.branch) not in leaves.claims:
        return True, f"no claim on {rec.node_id} for {rec.branch}"
    if ref := leaves.complete.get(rec.node_id):
        return True, f"{rec.node_id} is Complete on {ref}"
    if not Path(rec.worktree).is_dir():
        return False, f"worktree {rec.worktree} is gone"
    return None


def holding_slots(repo_root: Path, records: Iterable[WorkerRecord]) -> list[WorkerRecord]:
    """The active ``records`` that count toward ``policy.max_workers``: all but held workers whose leaf is over."""
    leaves = _Leaves(repo_root)
    return [r for r in records if r.active and not ((c := _cause(r, leaves)) and c[0])]


def orphans(repo_root: Path, records: Iterable[WorkerRecord] | None = None) -> dict[str, str]:
    """Worker id -> why, for each held worker whose leaf is Complete, whose claim is gone or whose worktree is."""
    leaves = _Leaves(repo_root)
    recs = list_records(repo_root, active_only=True) if records is None else records
    return {r.worker_id: c[1] for r in recs if (c := _cause(r, leaves))}


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
    return _end(repo_root, lambda r: (c := _cause(r, leaves)) and c[1])


def end_finished_workers(repo_root: Path, node_id: str) -> list[tuple[WorkerRecord, str]]:
    """``finish-this-task``: end ``node_id``'s idle and completed workers (a running one is left alone)."""
    return _end(repo_root, lambda r: r.node_id == node_id and r.state in HELD_STATES
                and f"{node_id} finished while {r.worker_id} was {r.state}")


# --- CLI glue: worker_cli.py sits at the line cap ---------------------------------------------------------------

def orphan_lines(gone: dict[str, str]) -> list[str]:
    if not gone:
        return []
    return [*(f"orphaned: {w} ({why})" for w, why in gone.items()), _HINT]


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
