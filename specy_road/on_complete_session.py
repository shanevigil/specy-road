"""Per-task ``on_complete`` session file under ``work/`` (do-next → finish-this-task)."""

from __future__ import annotations

from pathlib import Path

from specy_road.session_file_io import read_session_file, write_session_file

SESSION_VERSION = 1
SESSION_PREFIX = ".on-complete-"
SESSION_SUFFIX = ".yaml"


def on_complete_session_path(work_dir: Path, node_id: str) -> Path:
    """Path to ``work/.on-complete-<NODE_ID>.yaml``."""
    safe = node_id.replace("/", "_").replace("\\", "_")
    return work_dir / f"{SESSION_PREFIX}{safe}{SESSION_SUFFIX}"


def write_on_complete_session(
    path: Path,
    *,
    node_id: str,
    codename: str,
    on_complete: str,
) -> None:
    """Write session file; parent ``work_dir`` must exist."""
    write_session_file(path, SESSION_VERSION, {
        "node_id": node_id,
        "codename": codename,
        "on_complete": on_complete,
    })


def read_on_complete_session(
    path: Path,
    *,
    node_id: str,
    codename: str,
) -> str | None:
    """
    Return ``on_complete`` if file exists and matches ``node_id`` and ``codename``.
    Otherwise return None (stale or missing).
    """
    raw = read_session_file(path, SESSION_VERSION)
    if raw is None:
        return None
    if raw.get("node_id") != node_id or raw.get("codename") != codename:
        return None
    v = raw.get("on_complete")
    if isinstance(v, str) and v in ("auto", "merge", "pr"):
        return v
    return None


def remove_on_complete_session(path: Path) -> None:
    """Delete session file if present (ignore errors).

    Safety net only. Every caller here runs *after* its command's last commit,
    so staging a deletion would just leave a dirty index. ``finish-this-task``
    removes a tracked sidecar during its bookkeeping phase instead — see
    ``specy_road.finish_work_artifacts.cleanup_session_sidecar`` — which leaves
    nothing for this to do on the normal path.
    """
    try:
        path.unlink()
    except OSError:
        pass
