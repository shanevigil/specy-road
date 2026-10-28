"""The operations outbox: ``work/.workers/ops/<op-id>.yaml`` (slice 7a).

A mutating ``specy-road worker`` command may carry ``--op-id``; a retry with
the same id is answered from the first result instead of running twice. An
op id names **one** operation: a replay with a different kind, target or
arguments is refused rather than handed someone else's result. An op left
``pending`` is a crash marker, not a retry point: the command may or may
not have taken effect, so the retry is refused and the file names what to
inspect (the worker record and events) before removing it.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

_OP = re.compile(r"^[A-Za-z0-9._-]{1,80}$")


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _write_atomic(path: Path, text: str) -> None:
    from specy_road.worker_state import _write_atomic as write

    write(path, text)


def ops_dir(repo_root: Path) -> Path:
    from specy_road.worker_state import workers_dir

    return workers_dir(repo_root) / "ops"


def _error(msg: str) -> Exception:
    from specy_road.worker_state import WorkerError

    return WorkerError(msg)


def _op_path(repo_root: Path, op_id: str) -> Path:
    if not _OP.match(op_id):
        raise _error(f"op id {op_id!r}: letters, digits, '.', '_' or '-' (max 80)")
    return ops_dir(repo_root) / f"{op_id}.yaml"


def inputs_hash(inputs: dict[str, Any] | None) -> str | None:
    """A digest of every behaviour-affecting argument, so a replay with different inputs is refused."""
    if not inputs:
        return None
    import hashlib
    import json

    return hashlib.sha256(json.dumps(inputs, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]


def begin_op(repo_root: Path, op_id: str, kind: str, target: str | None = None,
             inputs: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Claim ``op_id``. Returns the earlier result when it already ran, else ``None`` (now pending).

    ``target`` is the worker id, or the node id for ``delegate``/``adopt``:
    a replay must name the same one, so one op id cannot answer a delegate
    on a different leaf with another leaf's worker.
    """
    from specy_road.worker_state import workers_lock

    path = _op_path(repo_root, op_id)
    with workers_lock(repo_root):
        if path.is_file():
            old = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            if old.get("state") == "pending":
                raise _error(f"op {op_id} is still pending (crashed?); pass a new --op-id or remove {path}")
            if old.get("kind") != kind or old.get("target") != target:
                raise _error(f"op {op_id} was a {old.get('kind')} on {old.get('target') or '-'}, "
                             f"not a {kind} on {target or '-'}; an op id names one operation")
            if old.get("inputs") != inputs_hash(inputs):
                raise _error(f"op {op_id} ran with different arguments; an op id names one operation")
            return old
        path.parent.mkdir(parents=True, exist_ok=True)
        _write_atomic(path, yaml.safe_dump({"op_id": op_id, "kind": kind, "target": target,
                                            "inputs": inputs_hash(inputs), "state": "pending",
                                            "at": _now()}, sort_keys=False))
    return None


def lookup_op(repo_root: Path, op_id: str, kind: str, target: str | None = None) -> dict[str, Any] | None:
    """The finished op under ``op_id`` when it was this ``kind`` on ``target``; ``None`` when there is none.

    For a retry whose inputs cannot be re-read (``message --file`` and the
    file is gone): the first result still answers, since the op id bound it.
    """
    path = _op_path(repo_root, op_id)
    if not path.is_file():
        return None
    old = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if old.get("state") == "pending":
        raise _error(f"op {op_id} is still pending (crashed?); pass a new --op-id or remove {path}")
    if old.get("kind") != kind or old.get("target") != target:
        raise _error(f"op {op_id} was a {old.get('kind')} on {old.get('target') or '-'}, "
                     f"not a {kind} on {target or '-'}; an op id names one operation")
    return old


def complete_op(repo_root: Path, op_id: str, result: dict[str, Any], *, ok: bool = True) -> None:
    path = _op_path(repo_root, op_id)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) if path.is_file() else {"op_id": op_id}
    data.update({"state": "applied" if ok else "failed", "result": result, "at": _now()})
    _write_atomic(path, yaml.safe_dump(data, sort_keys=False))
