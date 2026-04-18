"""Optimistic concurrency guards for PM GUI mutating API routes.

Drag-and-drop, dependency edits, and other PM mutations must "just work"
for the PM, even when several PMs are editing the same project, when
Cursor / IDEs are autosaving planning sheets, or when the toolkit's own
background ``git fetch`` / ``merge --ff-only`` is moving HEAD.

To get that, the guard validates a **narrow** fingerprint that only
includes files whose change actually invalidates the requested mutation
(the manifest + included chunks + registry — see
:func:`specy_road.pm_gui_fingerprint.outline_mutation_fingerprint`).
Activity in ``planning/``, ``constitution/``, ``shared/``, ``vision.md``,
or git HEAD does not invalidate the token, so noise from outside the
user's window of attention can no longer reject a legitimate edit.

The broad fingerprint is still emitted by ``GET /api/roadmap`` and
``GET /api/roadmap/fingerprint`` for the polling refresh, but it is
informational only — it never causes a 412.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import Header, HTTPException

from specy_road.gui_app_helpers import get_repo_root
from specy_road.pm_gui_fingerprint import outline_mutation_fingerprint

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
    """Raise 412 if the on-disk **narrow** outline fingerprint disagrees with the client's token.

    On mismatch, the response body always includes:

    * ``current_fingerprint`` — the freshest narrow token, suitable for
      the bundled UI to retry with directly;
    * ``retryable: true`` — hint that the bundled UI may absorb this
      via a transparent one-shot retry before surfacing the banner.

    The narrow fingerprint is computed only from the manifest + included
    chunks + registry, so it does not shift in response to autosaves,
    git fetches, HEAD movement, or any activity outside the roadmap's
    own data files.
    """
    current = outline_mutation_fingerprint(repo_root)
    if current == expected:
        return
    raise HTTPException(
        status_code=412,
        detail={
            "message": (
                "PM GUI data changed on disk since this client loaded it; "
                "refresh and retry."
            ),
            "current_fingerprint": current,
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
