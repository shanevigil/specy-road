"""In-memory status snapshots for PM GUI git auto-sync attempts."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

_LAST_FETCH_STATUS: dict[str, dict[str, Any]] = {}
_LAST_INTEGRATION_FF_STATUS: dict[str, dict[str, Any]] = {}


def _status_key(repo_root: Path) -> str:
    return str(repo_root.resolve())


def status_ok(*, remote: str, step: str) -> dict[str, Any]:
    return {
        "ok": True,
        "remote": remote,
        "step": step,
        "reason": None,
        "attempted_at_epoch_s": int(time.time()),
    }


def status_failure(
    *,
    remote: str,
    step: str,
    reason: str,
    error: str = "",
    returncode: int | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "ok": False,
        "remote": remote,
        "step": step,
        "reason": reason,
        "attempted_at_epoch_s": int(time.time()),
    }
    if error:
        out["error"] = error
    if returncode is not None:
        out["returncode"] = returncode
    return out


def set_last_registry_auto_fetch_status(repo_root: Path, status: dict[str, Any]) -> None:
    _LAST_FETCH_STATUS[_status_key(repo_root)] = dict(status)


def set_last_integration_auto_ff_status(repo_root: Path, status: dict[str, Any]) -> None:
    _LAST_INTEGRATION_FF_STATUS[_status_key(repo_root)] = dict(status)


def last_registry_auto_fetch_status(repo_root: Path) -> dict[str, Any] | None:
    st = _LAST_FETCH_STATUS.get(_status_key(repo_root))
    return dict(st) if isinstance(st, dict) else None


def last_integration_auto_ff_status(repo_root: Path) -> dict[str, Any] | None:
    st = _LAST_INTEGRATION_FF_STATUS.get(_status_key(repo_root))
    return dict(st) if isinstance(st, dict) else None
