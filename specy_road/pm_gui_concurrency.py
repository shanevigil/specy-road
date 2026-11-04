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

import contextlib
import threading
from collections.abc import Iterator
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

    If the fingerprint cannot be computed because the roadmap is
    transiently broken on disk (corrupt manifest, missing chunk,
    unreadable file), surface a **409 Conflict** with a human-readable
    hint pointing at ``specy-road validate``, instead of leaking a
    bare 500. The PM UI's transparent retry is wired for 4xx; a 500
    halts retries and confuses the user.
    """
    try:
        current = outline_mutation_fingerprint(repo_root)
    except (OSError, ValueError, RuntimeError, KeyError) as e:
        raise HTTPException(
            status_code=409,
            detail={
                "message": (
                    "Roadmap data is currently unreadable; cannot validate "
                    "the mutation token. Run `specy-road validate` and retry."
                ),
                "error": f"{type(e).__name__}: {e}",
                "retryable": False,
            },
        ) from e
    if current == expected:
        return
    raise HTTPException(
        status_code=412,
        detail={
            "message": (
                "PM GUI data changed on disk since this client loaded it; "
                "refresh and retry."
            ),
            # String-encoded so the browser's float64 ``Number`` cannot
            # lose precision when the client reuses this for the
            # transparent retry. Mirrors GET /api/roadmap/fingerprint.
            "current_fingerprint": str(current),
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


_NODE_WRITE_LOCKS: dict[str, threading.Lock] = {}
_NODE_WRITE_LOCKS_GUARD = threading.Lock()


@contextlib.contextmanager
def node_write_slot(
    repo_root: Path, node_id: str, x_pm_gui_fingerprint: str | None
) -> Iterator[None]:
    """One write at a time per node; a second concurrent write gets **409**.

    The fingerprint dependency runs before the handler, so two requests sent
    with the same token both pass it. Run in parallel, a title PATCH renames
    the planning sheet twice and the loser's rollback leaves the roadmap and
    ``planning/`` disagreeing (``planning file missing`` / ``orphan planning
    file``). The second request is refused instead of queued, and the token
    is checked again while the slot is held so a request that waited past
    another write still gets its 412.
    """
    with _NODE_WRITE_LOCKS_GUARD:
        lock = _NODE_WRITE_LOCKS.setdefault(node_id, threading.Lock())
    if not lock.acquire(blocking=False):
        raise HTTPException(
            status_code=409,
            detail={
                "message": (
                    f"another save for node {node_id} is still running; this one "
                    "was not applied. Wait for it to finish, refresh, and retry."
                ),
                "retryable": False,
            },
        )
    try:
        guard_pm_gui_write(repo_root, x_pm_gui_fingerprint)
        yield
    finally:
        lock.release()
