"""Worker records and event log under ``work/.workers/`` (slice 7a).

A worker is one leaf being implemented by one session on one vendor harness,
launched (or adopted) by the coordinator. ``prompt --channel cli`` ran such a
session and forgot it; this module is what remembers: a record per worker
(``<id>.yaml``, current state), an append-only event log (``<id>.events.jsonl``,
what happened, in order), and an outbox of operations (``ops/<op-id>.yaml``)
so a retried command is answered from its first result.

Files, not a daemon, and always in the **main** worktree like presence files
and review records: the coordinator's process may exit and come back, and a
worker in a linked worktree still writes into the one directory. Two rules
hold everything together. There is **one writer** per worker, named by the
lease (``broker`` while specy-road sends turns, ``human`` after a handoff,
``native`` for an adopted session we only watch); and the log is
**authoritative**: a vendor transcript is evidence, this log is what the
coordinator is entitled to assume (design note
``docs/design-notes/v0-3-1-worker-orchestration.md``, decisions D3 and D5).
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import threading
from collections.abc import Callable, Iterator
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from functools import cache
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from specy_road.git_subprocess import head_sha
from specy_road.review_files import reviews_root
from specy_road.runtime_paths import specy_road_package_dir

WORKERS_DIRNAME = ".workers"
HARNESSES = ("claude-code", "codex", "cursor", "generic")
#: A worker in one of these is over for good. ``completed`` is not: it still
#: owns its leaf and its slot (a review ``block`` goes back to it) until
#: ``terminate`` closes it.
TERMINAL_STATES = frozenset({"failed", "terminated"})
LEASE_HOLDERS = ("broker", "human", "native", "none")
FLAG_EXTERNAL = "possibly_modified_externally"
FLAG_RECONCILE = "needs_reconcile"
_ID = re.compile(r"^w-[0-9]{4,}$")


class WorkerError(Exception):
    """A record is missing, invalid, or the operation is not allowed in its state."""


class LeaseError(WorkerError):
    """The worker's single writer is someone else (``WORKER_LEASED_BY_HUMAN`` and kin)."""


@dataclass
class WorkerRecord:
    worker_id: str
    node_id: str
    harness: str
    model: str
    worktree: str
    state: str
    lease: dict[str, str]
    instruction_epoch: int
    attempt: int
    last_event_seq: int
    created: str
    updated: str
    provider_session_id: str | None = None
    branch: str | None = None
    pid: int | None = None
    flags: list[str] = field(default_factory=list)
    contract_hash: str | None = None
    checkpoint: dict[str, Any] | None = None
    billing_route: str | None = None

    @property
    def active(self) -> bool:
        return self.state not in TERMINAL_STATES

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class WorkerEvent:
    seq: int
    worker_id: str
    at: str
    type: str
    source: str
    authority: str
    summary: str
    epoch: int
    detail: dict[str, Any] | None = None
    op_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = {k: v for k, v in asdict(self).items() if v is not None}
        return d


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _write_atomic(path: Path, text: str) -> None:
    """Replace ``path`` in one step: the wrapper and the CLI both write records,
    and a reader must never see a half-written file."""
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


_THREAD_LOCKS: dict[str, threading.RLock] = {}
_LOCAL = threading.local()


@contextlib.contextmanager
def workers_lock(repo_root: Path) -> Iterator[None]:
    """One exclusive lock for every load-modify-save under ``work/.workers/``.

    The wrapper, the coordinator's commands and a hook all write records; a
    read-modify-write without the lock loses the other writer's change
    (``needs_reconcile`` set by ``reconcile`` while the wrapper streams, two
    ``delegate`` calls on one leaf). Re-entrant within a thread, so a mutation
    that appends an event takes it once; an ``RLock`` serialises threads of
    one process and ``flock`` serialises processes. ``fcntl`` is POSIX; on
    Windows only the thread lock applies, the state before this lock existed.
    """
    d = workers_dir(repo_root)
    d.mkdir(parents=True, exist_ok=True)
    key = str(d)
    depth = getattr(_LOCAL, "depth", None) or {}
    _LOCAL.depth = depth
    if depth.get(key, 0) > 0:
        depth[key] += 1
        try:
            yield
        finally:
            depth[key] -= 1
        return
    rlock = _THREAD_LOCKS.setdefault(key, threading.RLock())
    try:
        import fcntl
    except ImportError:  # Windows
        fcntl = None
    with rlock, (d / ".lock").open("a+") as f:
        if fcntl is not None:
            fcntl.flock(f, fcntl.LOCK_EX)
        depth[key] = 1
        try:
            yield
        finally:
            depth[key] = 0
            if fcntl is not None:
                fcntl.flock(f, fcntl.LOCK_UN)


def _refresh(repo_root: Path, rec: WorkerRecord) -> None:
    """Replace ``rec``'s fields with what is on disk, when a record exists there."""
    path = record_path(repo_root, rec.worker_id)
    if path.is_file():
        fresh = load_record(repo_root, rec.worker_id)
        rec.__dict__.update(fresh.__dict__)


def mutate(repo_root: Path, rec: WorkerRecord, fn: Callable[[WorkerRecord], None]) -> WorkerRecord:
    """Lock, reload from disk, apply ``fn``, save: the only safe way to change a record."""
    with workers_lock(repo_root):
        _refresh(repo_root, rec)
        fn(rec)
        save_record(repo_root, rec)
    return rec


@cache
def _validator(name: str) -> Draft202012Validator:
    path = specy_road_package_dir() / "schemas" / name
    return Draft202012Validator(json.loads(path.read_text(encoding="utf-8")))


def schema_errors(data: dict[str, Any], schema_name: str) -> list[str]:
    out = []
    for e in sorted(_validator(schema_name).iter_errors(data), key=lambda e: list(e.path)):
        loc = "/".join(str(x) for x in e.path) if e.path else "(root)"
        out.append(f"{loc}: {e.message}")
    return out


# --- paths -----------------------------------------------------------------

def workers_dir(repo_root: Path) -> Path:
    return reviews_root(repo_root).parent / WORKERS_DIRNAME


def record_path(repo_root: Path, worker_id: str) -> Path:
    if not _ID.match(worker_id):
        raise WorkerError(f"worker id {worker_id!r}: expected w-NNNN")
    return workers_dir(repo_root) / f"{worker_id}.yaml"


def events_path(repo_root: Path, worker_id: str) -> Path:
    return record_path(repo_root, worker_id).with_suffix(".events.jsonl")


# --- records ---------------------------------------------------------------

def new_worker_id(repo_root: Path) -> str:
    d = workers_dir(repo_root)
    taken = [int(p.stem[2:]) for p in d.glob("w-*.yaml")] if d.is_dir() else []
    return f"w-{(max(taken) + 1 if taken else 1):04d}"


def save_record(repo_root: Path, rec: WorkerRecord) -> Path:
    rec.updated = _now()
    data = rec.to_dict()
    errs = schema_errors(data, "worker-record.schema.json")
    if errs:
        raise WorkerError(f"{rec.worker_id}: " + "; ".join(errs))
    path = record_path(repo_root, rec.worker_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_atomic(path, yaml.safe_dump(data, sort_keys=False))
    return path


def load_record(repo_root: Path, worker_id: str) -> WorkerRecord:
    path = record_path(repo_root, worker_id)
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as e:
        raise WorkerError(f"{worker_id}: no record ({e})") from None
    except yaml.YAMLError as e:
        raise WorkerError(f"{worker_id}: record is not valid YAML: {e}") from None
    if not isinstance(raw, dict):
        raise WorkerError(f"{worker_id}: record is not a mapping")
    errs = schema_errors(raw, "worker-record.schema.json")
    if errs:
        raise WorkerError(f"{worker_id}: " + "; ".join(errs))
    return WorkerRecord(**raw)


def list_records(repo_root: Path, *, active_only: bool = False) -> list[WorkerRecord]:
    d = workers_dir(repo_root)
    if not d.is_dir():
        return []
    out = []
    for p in sorted(d.glob("w-*.yaml")):
        try:
            out.append(load_record(repo_root, p.stem))
        except WorkerError:
            continue
    return [r for r in out if r.active] if active_only else out


def active_for_node(repo_root: Path, node_id: str) -> WorkerRecord | None:
    """The live worker on ``node_id``, if any: delegating again must return it, not launch twice."""
    for r in list_records(repo_root, active_only=True):
        if r.node_id == node_id:
            return r
    return None


def create_record(repo_root: Path, node_id: str, harness: str, model: str, worktree: Path, *,
                  branch: str | None = None, contract_hash: str | None = None,
                  billing_route: str | None = None, lease: str = "broker") -> WorkerRecord:
    if harness not in HARNESSES:
        raise WorkerError(f"harness {harness!r}: expected one of {', '.join(HARNESSES)}")
    with workers_lock(repo_root):
        attempts = [r.attempt for r in list_records(repo_root) if r.node_id == node_id]
        now = _now()
        rec = WorkerRecord(new_worker_id(repo_root), node_id, harness, model, str(Path(worktree).resolve()),
                           "starting", {"holder": lease, "since": now}, 0, max(attempts, default=0) + 1, 0,
                           now, now, branch=branch, contract_hash=contract_hash, billing_route=billing_route)
        save_record(repo_root, rec)
        append_event(repo_root, rec, "started", source="broker",
                     summary=f"delegated {node_id} to {harness}/{model} (attempt {rec.attempt})")
    return rec


def set_state(repo_root: Path, rec: WorkerRecord, state: str, *, pid: int | None = ...) -> WorkerRecord:
    def fn(r: WorkerRecord) -> None:
        r.state = state
        if pid is not ...:
            r.pid = pid
    return mutate(repo_root, rec, fn)


def add_flag(repo_root: Path, rec: WorkerRecord, flag: str) -> None:
    mutate(repo_root, rec, lambda r: r.flags.append(flag) if flag not in r.flags else None)


def clear_flag(repo_root: Path, rec: WorkerRecord, flag: str) -> None:
    mutate(repo_root, rec, lambda r: r.flags.remove(flag) if flag in r.flags else None)


# --- events ----------------------------------------------------------------

def append_event(repo_root: Path, rec: WorkerRecord, type_: str, *, source: str, summary: str,
                 authority: str = "system", detail: dict[str, Any] | None = None,
                 op_id: str | None = None) -> WorkerEvent:
    """Append one event and bump the record's ``last_event_seq`` in the same step.

    Under the workers lock, against the record as it is on disk: the caller's
    copy may be stale (the wrapper holds one for the whole run).
    """
    with workers_lock(repo_root):
        _refresh(repo_root, rec)
        ev = WorkerEvent(rec.last_event_seq + 1, rec.worker_id, _now(), type_, source, authority,
                         (summary or "(empty)")[:500], rec.instruction_epoch, detail, op_id)
        data = ev.to_dict()
        errs = schema_errors(data, "worker-event.schema.json")
        if errs:
            raise WorkerError(f"{rec.worker_id} event: " + "; ".join(errs))
        path = events_path(repo_root, rec.worker_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(data, sort_keys=True) + "\n")
        rec.last_event_seq = ev.seq
        save_record(repo_root, rec)
    return ev


def events_since(repo_root: Path, worker_id: str, seq: int = 0) -> list[WorkerEvent]:
    """Events with ``seq`` greater than the given one, in order; malformed lines are skipped."""
    path = events_path(repo_root, worker_id)
    if not path.is_file():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if isinstance(d, dict) and not schema_errors(d, "worker-event.schema.json") and d["seq"] > seq:
            out.append(WorkerEvent(**d))
    return out


# --- lease, checkpoint, intervention ---------------------------------------

def require_writer(rec: WorkerRecord, holder: str = "broker") -> None:
    """Raise unless ``holder`` may send the worker a turn now."""
    have = rec.lease.get("holder")
    if have == holder:
        return
    code = {"human": "WORKER_LEASED_BY_HUMAN", "native": "WORKER_NATIVE_OWNED"}.get(have, "WORKER_NO_WRITER")
    raise LeaseError(f"{code}: {rec.worker_id} is leased to {have}; "
                     + ("run `specy-road worker reclaim` first" if have == "human" else "it cannot be written"))


def set_lease(repo_root: Path, rec: WorkerRecord, holder: str) -> None:
    if holder not in LEASE_HOLDERS:
        raise WorkerError(f"lease holder {holder!r}: expected one of {', '.join(LEASE_HOLDERS)}")
    mutate(repo_root, rec, lambda r: setattr(r, "lease", {"holder": holder, "since": _now()}))


def take_checkpoint(repo_root: Path, rec: WorkerRecord, native_turn: str | None = None) -> dict[str, Any]:
    """Remember where the worktree and session stood; a reclaim diffs from here."""
    cp = {"git_head": head_sha(Path(rec.worktree)), "native_turn": native_turn, "at": _now()}
    mutate(repo_root, rec, lambda r: setattr(r, "checkpoint", cp))
    return cp


def record_intervention(repo_root: Path, rec: WorkerRecord, summary: str, *, source: str = "human",
                        detail: dict[str, Any] | None = None) -> WorkerEvent:
    """A human direction reached the worker: new epoch, one authoritative event."""
    with workers_lock(repo_root):
        mutate(repo_root, rec, lambda r: setattr(r, "instruction_epoch", r.instruction_epoch + 1))
        return append_event(repo_root, rec, "intervention", source=source, authority="human_authoritative",
                            summary=summary, detail=detail)


# The operations outbox lives in worker_outbox; re-exported here for callers.

__all__ = [n for n in dir() if not n.startswith("_")]
from specy_road.worker_outbox import begin_op, complete_op  # noqa: E402,F401 — re-exported for callers
