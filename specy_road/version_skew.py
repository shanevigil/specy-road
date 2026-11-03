"""Warn when the running specy-road is older than the version a project records."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from specy_road import __version__
from specy_road.agents_md_block import AGENTS_MD
from specy_road.managed_block import HTML_COMMENT, _split
from specy_road.runtime_paths import git_root
from specy_road.toolkit_version import running_toolkit_version

__all__ = ["recorded_toolkit_version", "running_toolkit_version", "warn_if_running_version_older"]

_VERSION = re.compile(r"^(\d+(?:\.\d+)*)(?:(a|b|rc)(\d+))?$", re.IGNORECASE)
_AGENTS_WRITTEN = re.compile(r"Written by specy-road (\S+)")
_MINIMUM_LINE = re.compile(r"\(minimum (\S+)\)")
_PRE = {"a": 0, "b": 1, "rc": 2}


def _version_sort_key(version: str) -> tuple[int, ...]:
    stem = version.strip().split("+", 1)[0]
    m = _VERSION.match(stem)
    if not m:
        return (0,)
    release = tuple(int(p) for p in m.group(1).split("."))
    pre = m.group(2)
    return (*release, 3, 0) if pre is None else (*release, _PRE[pre.lower()], int(m.group(3)))


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8") if path.is_file() else ""
    except (OSError, UnicodeDecodeError):
        return ""


def recorded_toolkit_version(project: Path) -> tuple[str, str] | None:
    checkout = git_root(project) or project.resolve()
    candidates: list[tuple[str, str]] = []
    try:
        raw = json.loads(_read_text(checkout / ".specyrd" / "manifest.json") or "null")
    except json.JSONDecodeError:
        raw = None
    recorded = str(raw.get("specyrd_version") or "").strip() if isinstance(raw, dict) else ""
    if recorded:
        candidates.append((recorded, ".specyrd/manifest.json"))
    _before, block, _after = _split(_read_text(project / AGENTS_MD), HTML_COMMENT)
    if block:
        for pattern in (_AGENTS_WRITTEN, _MINIMUM_LINE):
            m = pattern.search(block)
            if m:
                candidates.append((m.group(1), AGENTS_MD))
    if not candidates:
        return None
    best = max(candidates, key=lambda item: _version_sort_key(item[0]))
    sources = sorted({where for ver, where in candidates if ver == best[0]})
    where = sources[0] if len(sources) == 1 else " and ".join(sources)
    return best[0], where


def warn_if_running_version_older(project: Path) -> None:
    found = recorded_toolkit_version(project)
    if found is None:
        return
    recorded, where = found
    if _version_sort_key(__version__) >= _version_sort_key(recorded):
        return
    print(
        f"specy-road: warning — specy-road {__version__} is running but this project records "
        f"{recorded} ({where}); an older install earlier on PATH is the usual cause. "
        "Check `which specy-road` and `specy-road --version`, then reinstall with "
        "`pipx install specy-road` or `uv tool install specy-road`.",
        file=sys.stderr,
    )
