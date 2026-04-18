"""Optimistic concurrency guards for PM GUI mutating API routes.

The mutation guard's job is to make drag-and-drop "just work" for the PM
even when several PMs (or several browser tabs) are editing concurrently
and the toolkit's own background ``git fetch`` / ``merge --ff-only`` runs
between the GET that issued a token and the POST that uses it.

To do that the guard:

* always 412s when the on-disk fingerprint disagrees with the client's
  token (the on-disk snapshot is the canonical source of truth);
* re-runs the GET-side auto-fetch / auto-FF side effects so the
  ``current_fingerprint`` returned to the client is the same value
  ``GET /api/roadmap/fingerprint`` would return *right now*; and
* tags the response body with ``retryable: true`` so the bundled UI
  can transparently re-issue the mutation once with the fresh token
  before showing the "Roadmap or workspace changed elsewhere" banner.

Default behavior — no env switch needed.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import Header, HTTPException

from specy_road.gui_app_helpers import get_repo_root
from specy_road.pm_gui_fingerprint import pm_gui_mutation_fingerprint

PM_GUI_FINGERPRINT_HEADER = "X-PM-Gui-Fingerprint"


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


def _refresh_fingerprint_through_get_side_effects(repo_root: Path) -> int:
    """Recompute fingerprint after running the same auto-fetch / auto-FF the GET endpoints run.

    Done here so the ``current_fingerprint`` returned in the 412 body is
    the same value the next ``GET /api/roadmap/fingerprint`` would return —
    letting the client retry succeed without an extra round-trip.
    """
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
    return pm_gui_mutation_fingerprint(repo_root)


def require_pm_gui_mutation_fingerprint(repo_root: Path, expected: int) -> None:
    """Raise 412 if on-disk state no longer matches the client's expected fingerprint.

    On mismatch, the response body always includes:

    * ``current_fingerprint`` — the freshest token the server can produce,
      already accounting for any background git sync this request may
      have triggered;
    * ``retryable: true`` — hint to the bundled UI that this 412 is the
      ordinary "two concurrent writers raced" case; the client should
      refresh and re-issue the same mutation exactly once before
      surfacing the banner.
    """
    current = pm_gui_mutation_fingerprint(repo_root)
    if current == expected:
        return
    refreshed = _refresh_fingerprint_through_get_side_effects(repo_root)
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


def guard_pm_gui_write(repo_root: Path, x_pm_gui_fingerprint: str | None) -> None:
    """Parse header and require fingerprint match (428 / 412 retryable)."""
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
