"""Merge ``roadmap/registry.yaml`` from the remote integration branch and from ``feature/rm-*`` into the PM GUI payload.

Reads (after ``git fetch``) ``refs/remotes/<remote>/<integration_branch>`` first, then ``feature/rm-*`` — ``HEAD``
entries win on duplicate ``node_id``; remote sources fill gaps (integration branch before feature refs).

Primary control: **Settings** → ``pm_gui.registry_remote_overlay`` in ``~/.specy-road/gui-settings.json``
(default **on** for new profiles; still requires Git remote repo/token and successful **Test Git**).
Optional env override: ``SPECY_ROAD_GUI_REGISTRY_REMOTE_OVERLAY=0`` forces off; ``=1`` forces on.

Optional fast-forward of the **integration branch** (``git fetch`` + ``git merge --ff-only``) is controlled by
``pm_gui.integration_branch_auto_ff`` and ``SPECY_ROAD_GUI_AUTO_INTEGRATION_FF``; see ``maybe_auto_integration_ff``
and ``describe_integration_branch_auto_ff``.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import Any

from specy_road.git_sync_status import (
    last_integration_auto_ff_status,
    last_registry_auto_fetch_status,
    set_last_integration_auto_ff_status,
    set_last_registry_auto_fetch_status,
    status_failure,
    status_ok,
)
from specy_road.git_subprocess import (
    current_branch_name,
    is_git_worktree,
    run,
    working_tree_clean,
)
from specy_road.git_workflow_config import resolve_integration_defaults
from specy_road.pm_integration_registry import (
    describe_integration_branch_auto_ff as _describe_integration_branch_auto_ff,
)
from specy_road.registry_remote_overlay_merge import (
    list_remote_feature_rm_refs,
    merge_registry_with_remote_overlay,
    read_registry_at_ref,
    remote_feature_refs_fingerprint_addendum,
    resolve_git_remote,
    roadmap_fingerprint_with_remote_refs,
)
from specy_road.bundled_scripts.roadmap_gui_settings import effective_settings_for_repo  # noqa: E402

_GIT_SYNC_LOCK = threading.Lock()
_LAST_FETCH_MONO: dict[str, float] = {}
_LAST_INTEGRATION_FF_MONO: dict[str, float] = {}
_LOG = logging.getLogger(__name__)


def _sync_status_key(repo_root: Path) -> str:
    return str(repo_root.resolve())


def describe_integration_branch_auto_ff(
    repo_root: Path,
) -> dict[str, Any] | None:
    """Backward-compatible export for PM API route imports."""
    out = _describe_integration_branch_auto_ff(repo_root)
    if out is None:
        return None
    status = last_integration_auto_ff_status(repo_root)
    if status is not None:
        out = dict(out)
        out["last_auto_ff_attempt"] = status
    return out


def registry_remote_overlay_enabled(repo_root: Path | None = None) -> bool:
    """True when overlay merge should run: env override, else settings + Test Git + repo/token."""
    v = os.environ.get("SPECY_ROAD_GUI_REGISTRY_REMOTE_OVERLAY", "").strip().lower()
    if v in ("0", "false", "no", "off"):
        return False
    if v in ("1", "true", "yes", "on"):
        return True
    if repo_root is None:
        return False
    eff = effective_settings_for_repo(repo_root)
    pm = eff.get("pm_gui") if isinstance(eff.get("pm_gui"), dict) else {}
    if not pm.get("registry_remote_overlay"):
        return False
    from specy_road.bundled_scripts.pm_gui_git_remote_verify import get_git_remote_tested_ok

    if not get_git_remote_tested_ok(repo_root):
        return False
    gr = eff.get("git_remote") or {}
    return bool(str(gr.get("repo") or "").strip() and str(gr.get("token") or "").strip())


def integration_branch_auto_ff_enabled(repo_root: Path | None = None) -> bool:
    """True when periodic fast-forward of the integration branch is allowed (settings or env)."""
    v = os.environ.get("SPECY_ROAD_GUI_AUTO_INTEGRATION_FF", "").strip().lower()
    if v in ("0", "false", "no", "off"):
        return False
    if v in ("1", "true", "yes", "on"):
        return True
    if repo_root is None:
        return False
    eff = effective_settings_for_repo(repo_root)
    pm = eff.get("pm_gui") if isinstance(eff.get("pm_gui"), dict) else {}
    return pm.get("integration_branch_auto_ff") is True


def _integration_ff_interval_s() -> float:
    raw = os.environ.get("SPECY_ROAD_GUI_INTEGRATION_FF_INTERVAL_S", "").strip()
    if raw:
        try:
            return max(1.0, min(float(raw), 3600.0))
        except ValueError:
            pass
    raw_iv = os.environ.get("SPECY_ROAD_GUI_REGISTRY_FETCH_INTERVAL_S", "").strip()
    try:
        interval = float(raw_iv) if raw_iv else 5.0
    except ValueError:
        interval = 5.0
    return max(1.0, min(interval, 3600.0))


def _record_and_log_ff_failure(
    repo_root: Path,
    *,
    remote: str,
    base: str,
    step: str,
    reason: str,
    error: str,
    returncode: int | None = None,
) -> None:
    set_last_integration_auto_ff_status(
        repo_root,
        status_failure(
            remote=remote,
            step=step,
            reason=reason,
            error=error,
            returncode=returncode,
        ),
    )
    _LOG.warning(
        "integration auto-ff %s failed for %s (remote=%s, base=%s%s): %s",
        step,
        repo_root,
        remote,
        base,
        f", rc={returncode}" if returncode is not None else "",
        error or "<no error output>",
    )


def _record_and_log_fetch_failure(
    repo_root: Path,
    *,
    remote: str,
    reason: str,
    error: str,
    returncode: int | None = None,
) -> None:
    set_last_registry_auto_fetch_status(
        repo_root,
        status_failure(
            remote=remote,
            step="fetch",
            reason=reason,
            error=error,
            returncode=returncode,
        ),
    )
    _LOG.warning(
        "registry overlay auto-fetch failed for %s (remote=%s%s): %s",
        repo_root,
        remote,
        f", rc={returncode}" if returncode is not None else "",
        error or "<no error output>",
    )


def maybe_auto_integration_ff(repo_root: Path) -> None:
    """Best-effort integration branch fetch + ``merge --ff-only``."""
    if not integration_branch_auto_ff_enabled(repo_root):
        return
    if not is_git_worktree(repo_root):
        return
    base, remote, _warns = resolve_integration_defaults(
        repo_root,
        explicit_base=None,
        explicit_remote=None,
    )
    cur = current_branch_name(repo_root)
    if not cur or cur != base:
        return
    if not working_tree_clean(repo_root):
        return
    interval = _integration_ff_interval_s()
    key = str(repo_root.resolve())
    now = time.monotonic()
    rname = (remote or "").strip() or "origin"
    with _GIT_SYNC_LOCK:
        if key in _LAST_INTEGRATION_FF_MONO:
            last = _LAST_INTEGRATION_FF_MONO[key]
            if now - last < interval:
                return
        _LAST_INTEGRATION_FF_MONO[key] = now
        try:
            r_fetch = run(["fetch", "--quiet", rname], repo_root, timeout=120.0)
            if not r_fetch.ok:
                _record_and_log_ff_failure(
                    repo_root,
                    remote=rname,
                    base=base,
                    step="fetch",
                    reason=r_fetch.failure or "non_zero_exit",
                    error=r_fetch.message,
                    returncode=r_fetch.code,
                )
                return
            r_merge = run(["merge", "--ff-only", f"{rname}/{base}"], repo_root, timeout=120.0)
            if not r_merge.ok:
                _record_and_log_ff_failure(
                    repo_root,
                    remote=rname,
                    base=base,
                    step="merge_ff_only",
                    reason=r_merge.failure or "non_zero_exit",
                    error=r_merge.message,
                    returncode=r_merge.code,
                )
                return
            set_last_integration_auto_ff_status(
                repo_root,
                status_ok(remote=rname, step="merge_ff_only"),
            )
        except OSError as exc:
            _record_and_log_ff_failure(
                repo_root,
                remote=rname,
                base=base,
                step="fetch_or_merge_ff_only",
                reason="os_error",
                error=str(exc),
            )


def maybe_auto_git_fetch(repo_root: Path, remote: str) -> None:
    """Best-effort ``git fetch`` for ``remote``; throttled by interval; errors ignored."""
    af = os.environ.get("SPECY_ROAD_GUI_REGISTRY_AUTO_FETCH", "").strip().lower()
    if af in ("0", "false", "no", "off"):
        return
    if not is_git_worktree(repo_root):
        return
    raw_iv = os.environ.get("SPECY_ROAD_GUI_REGISTRY_FETCH_INTERVAL_S", "").strip()
    try:
        interval = float(raw_iv) if raw_iv else 5.0
    except ValueError:
        interval = 5.0
    interval = max(1.0, min(interval, 3600.0))
    key = _sync_status_key(repo_root)
    now = time.monotonic()
    rname = (remote or "").strip() or "origin"
    with _GIT_SYNC_LOCK:
        if key in _LAST_FETCH_MONO:
            last = _LAST_FETCH_MONO[key]
            if now - last < interval:
                return
        _LAST_FETCH_MONO[key] = now
        try:
            r_fetch = run(["fetch", "--quiet", rname], repo_root, timeout=120.0)
            if not r_fetch.ok:
                _record_and_log_fetch_failure(
                    repo_root,
                    remote=rname,
                    reason=r_fetch.failure or "non_zero_exit",
                    error=r_fetch.message,
                    returncode=r_fetch.code,
                )
                return
            set_last_registry_auto_fetch_status(
                repo_root,
                status_ok(remote=rname, step="fetch"),
            )
        except OSError as exc:
            _record_and_log_fetch_failure(
                repo_root,
                remote=rname,
                reason="os_error",
                error=str(exc),
            )
