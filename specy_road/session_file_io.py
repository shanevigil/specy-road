"""Read and write the versioned YAML session files under ``work/``.

The milestone rollup session (``work/.milestone-session.yaml``) and the
per-task ``on_complete`` sessions (``work/.on-complete-<NODE_ID>.yaml``) share
one shape: a YAML mapping whose ``version`` key names its format. Each module
keeps its own fields and checks; this one writes the file and reads it back.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def write_session_file(path: Path, version: int, fields: dict[str, Any]) -> None:
    """Write ``{"version": version, **fields}`` to ``path`` as block YAML, keys in order.

    The parent directory is created when missing.
    """
    doc = {"version": version, **fields}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.dump(doc, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def read_session_file(path: Path, version: int) -> dict[str, Any] | None:
    """The mapping in ``path`` when it parses and its ``version`` is ``version``; else ``None``.

    A missing, unreadable or malformed file, or one written in another format
    version, reads as no session.
    """
    if not path.is_file():
        return None
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return None
    if not isinstance(raw, dict) or raw.get("version") != version:
        return None
    return raw
