"""Stub version skew checks (library parts of ``refresh_stubs``)."""

from __future__ import annotations

import sys
from pathlib import Path

from specy_road import __version__
from specy_road.git_subprocess import git_root
from specy_road.specyrd_init import _load_manifest

MANIFEST_REL = Path(".specyrd") / "manifest.json"


def stubs_are_stale(start: Path) -> str | None:
    checkout = git_root(start) or start
    if not (checkout / MANIFEST_REL).is_file():
        return None
    manifest = _load_manifest(checkout)
    if not manifest.get("agents"):
        return None
    recorded = str(manifest.get("specyrd_version") or "")
    return recorded if recorded and recorded != __version__ else None


def warn_if_stubs_stale(start: Path) -> None:
    recorded = stubs_are_stale(start)
    if recorded is None:
        return
    print(
        f"specyrd: warning — IDE stubs were installed by specyrd {recorded} "
        f"but specy-road {__version__} is running, so commands added since "
        "then have no stub. Run: specy-road refresh-stubs",
        file=sys.stderr,
    )
