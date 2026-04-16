"""Per-task ``on_complete`` session file under ``work/`` (do-next → finish-this-task)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

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
    doc: dict[str, Any] = {
        "version": SESSION_VERSION,
        "node_id": node_id,
        "codename": codename,
        "on_complete": on_complete,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.dump(doc, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


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
    if not path.is_file():
        return None
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return None
    if not isinstance(raw, dict):
        return None
    if raw.get("version") != SESSION_VERSION:
        return None
    if raw.get("node_id") != node_id or raw.get("codename") != codename:
        return None
    v = raw.get("on_complete")
    if isinstance(v, str) and v in ("auto", "merge", "pr"):
        return v
    return None


def remove_on_complete_session(path: Path) -> None:
    """Delete session file if present (ignore errors)."""
    try:
        path.unlink()
    except OSError:
        pass
