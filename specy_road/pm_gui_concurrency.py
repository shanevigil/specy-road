"""Optimistic concurrency guards for PM GUI mutating API routes."""

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
