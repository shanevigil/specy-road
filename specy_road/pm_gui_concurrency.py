"""Optimistic concurrency guards for PM GUI mutating API routes."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import Header, HTTPException

from specy_road.gui_app_helpers import get_repo_root
from specy_road.pm_gui_fingerprint import pm_gui_mutation_fingerprint

PM_GUI_FINGERPRINT_HEADER = "X-PM-Gui-Fingerprint"

#: Env var: when set to a truthy value, mutating routes use the lenient
#: dep that absorbs in-server auto-FF / auto-fetch fingerprint shifts. The
#: server marks such 412s as ``retryable: true`` so the client can
#: transparently retry once. Default behavior (no env var) is unchanged.
PM_AUTO_RETRY_AUTOFF_ENV = "SPECY_ROAD_GUI_PM_AUTO_RETRY_AUTOFF"


def parse_pm_gui_fingerprint_header(raw: str | None) -> int:
    """Require a base-10 integer fingerprint header (428 if missing)."""
    if raw is None or not str(raw).strip():
        raise HTTPException(
            status_code=428,
            detail={
                "message": (
                    f"{PM_GUI_FINGERPRINT_HEADER} header is required for this request."
                ),
                "current_fingerprint": None,
            },
        )
    try:
        return int(str(raw).strip(), 10)
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"invalid {PM_GUI_FINGERPRINT_HEADER}: expected integer",
        ) from e


def require_pm_gui_mutation_fingerprint(repo_root: Path, expected: int) -> None:
    """Raise 412 if on-disk state no longer matches the client's expected fingerprint."""
    current = pm_gui_mutation_fingerprint(repo_root)
    if current != expected:
        raise HTTPException(
            status_code=412,
            detail={
                "message": (
                    "PM GUI data changed on disk since this client loaded it; "
                    "refresh and retry."
                ),
                "current_fingerprint": current,
            },
        )


def guard_pm_gui_write(repo_root: Path, x_pm_gui_fingerprint: str | None) -> None:
    """Parse header and require fingerprint match (428 / 412)."""
    expected = parse_pm_gui_fingerprint_header(x_pm_gui_fingerprint)
    require_pm_gui_mutation_fingerprint(repo_root, expected)


def require_pm_gui_write_header(
    x_pm_gui_fingerprint: str | None = Header(
        None,
        alias=PM_GUI_FINGERPRINT_HEADER,
    ),
) -> None:
    """FastAPI dependency: require ``X-PM-Gui-Fingerprint`` before mutating repo state."""
    guard_pm_gui_write(get_repo_root(), x_pm_gui_fingerprint)


def autoff_grace_enabled() -> bool:
    """True when mutating routes should absorb in-server auto-FF/fetch shifts."""
    v = os.environ.get(PM_AUTO_RETRY_AUTOFF_ENV, "").strip().lower()
    return v in ("1", "true", "yes", "on")


def guard_pm_gui_write_with_autoff_grace(
    repo_root: Path, x_pm_gui_fingerprint: str | None
) -> None:
    """Like :func:`guard_pm_gui_write`, but tags 412s as ``retryable: true``.

    The auto-FF race in production has the form: GET #1 captures token A;
    GET #2 (e.g. polling refresh, or a sibling tab) runs ``maybe_auto_git_fetch``
    + ``maybe_auto_integration_ff`` and returns token B; user drags using
    token A; POST arrives with A but disk now matches B (or even C). The
    on-disk snapshot is canonical; we cannot accept token A. What we *can*
    do is tell the client this 412 is transient ("retryable") so the
    client retries exactly once with the fresh token before showing the
    user-visible banner.

    This guard always recomputes via the GET-side helper so that the
    ``current_fingerprint`` returned to the client is the same value
    ``GET /api/roadmap/fingerprint`` would return *right now* — letting
    the client's transparent retry succeed without an extra round-trip.
    """
    expected = parse_pm_gui_fingerprint_header(x_pm_gui_fingerprint)
    current = pm_gui_mutation_fingerprint(repo_root)
    if current == expected:
        return
    # Lazy import to avoid cycle at module import time.
    from specy_road.registry_remote_overlay import (
        maybe_auto_git_fetch,
        maybe_auto_integration_ff,
        registry_remote_overlay_enabled,
        resolve_git_remote,
    )

    if registry_remote_overlay_enabled(repo_root):
        maybe_auto_git_fetch(repo_root, resolve_git_remote(repo_root))
    maybe_auto_integration_ff(repo_root)
    refreshed = pm_gui_mutation_fingerprint(repo_root)
    raise HTTPException(
        status_code=412,
        detail={
            "message": (
                "PM GUI data changed on disk since this client loaded it; "
                "refresh and retry."
            ),
            "current_fingerprint": refreshed,
            "retryable": True,
        },
    )


def require_pm_gui_write_header_lenient(
    x_pm_gui_fingerprint: str | None = Header(
        None,
        alias=PM_GUI_FINGERPRINT_HEADER,
    ),
) -> None:
    """FastAPI dep: opt-in counterpart to :func:`require_pm_gui_write_header`.

    Wired in :mod:`specy_road.gui_app_routes_nodes` (and friends) only when
    :data:`PM_AUTO_RETRY_AUTOFF_ENV` is truthy.
    """
    guard_pm_gui_write_with_autoff_grace(get_repo_root(), x_pm_gui_fingerprint)


def require_pm_gui_write_header_env_aware(
    x_pm_gui_fingerprint: str | None = Header(
        None,
        alias=PM_GUI_FINGERPRINT_HEADER,
    ),
) -> None:
    """Resolve the right guard at request time based on the env flag."""
    if autoff_grace_enabled():
        guard_pm_gui_write_with_autoff_grace(get_repo_root(), x_pm_gui_fingerprint)
    else:
        guard_pm_gui_write(get_repo_root(), x_pm_gui_fingerprint)
