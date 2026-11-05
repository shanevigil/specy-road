"""Shared documentation zones: directory touch zones that do not make leaves overlap.

Almost every leaf names ``planning/`` and ``shared/`` in its touch zones, so the
plain overlap rule (same path, or one a directory prefix of the other) put every
ready leaf in its own ``grind-session --plan`` batch. A configured shared zone,
named as a zone itself, overlaps nothing; two leaves naming the same file (or the
same subdirectory) under it still overlap. Configured with ``grind.shared_zones``
in ``roadmap/git-workflow.yaml`` (schema-checked); an empty list turns it off.
"""

from __future__ import annotations

import posixpath
import re
from collections.abc import Iterable
from pathlib import Path

from specy_road.git_workflow_config import load_git_workflow_config

DEFAULT_SHARED_ZONES: tuple[str, ...] = ("planning/", "shared/")


def norm_zone(zone: str) -> str:
    """POSIX-normalized zone: strip spaces and ``./``, collapse ``//`` and ``x/../``;
    a trailing ``/`` (a directory zone) is kept. ``./`` alone normalizes to ``""``."""
    raw = zone.strip()
    path = posixpath.normpath(re.sub(r"/{2,}", "/", raw)) if raw else "."
    path = "" if path == "." else path
    return path + "/" if path and raw.endswith("/") else path


def zone_key(zone: str) -> str:
    """:func:`norm_zone` without the trailing ``/``: the path two zones compare by."""
    return norm_zone(zone).rstrip("/")


def in_zone_tree(path: str, zone: str) -> bool:
    """``path`` is ``zone`` itself or under it."""
    p, z = zone_key(path), zone_key(zone)
    return p == z or p.startswith(z + "/")


def unique_zones(zones: Iterable[str]) -> list[str]:
    """``zones`` with spellings of one path (:func:`zone_key`) collapsed to the first."""
    seen: dict[str, str] = {}
    for zone in zones:
        seen.setdefault(zone_key(zone), zone)
    return list(seen.values())


def is_shared_zone(zone: str, shared: Iterable[str]) -> bool:
    return zone_key(zone) in {zone_key(z) for z in shared}


def resolve_shared_zones(repo_root: Path) -> tuple[str, ...]:
    """``grind.shared_zones`` from ``roadmap/git-workflow.yaml``, else the default.

    An unreadable config yields the default, as the other git-workflow settings do.
    """
    data, err = load_git_workflow_config(repo_root)
    zones = ((data or {}).get("grind") or {}).get("shared_zones") if not err else None
    return DEFAULT_SHARED_ZONES if zones is None else tuple(unique_zones(zones))


def zones_overlap(a: str, b: str, shared: Iterable[str]) -> bool:
    """The one overlap rule ``grind-session --plan`` and ``validate`` share.

    Both zones are normalized (:func:`norm_zone`); they overlap when one is the
    other or under it, unless either is itself a shared zone.
    """
    if not (in_zone_tree(a, b) or in_zone_tree(b, a)):
        return False
    return not (is_shared_zone(a, shared) or is_shared_zone(b, shared))


def effective_overlap(
    a_zones: Iterable[str], b_zones: Iterable[str], shared: Iterable[str]
) -> tuple[str, str] | None:
    """First ``(a zone, b zone)`` pair that :func:`zones_overlap`."""
    shared = tuple(shared)
    b_zones = list(b_zones)
    for a in a_zones:
        for b in b_zones:
            if zones_overlap(a, b, shared):
                return a, b
    return None


def ignored_shared_zones(
    zones: dict[str, list[str]], leaf_ids: Iterable[str], shared: Iterable[str]
) -> list[str]:
    """Shared zones that would have held a leaf back: one of ``leaf_ids`` names the
    zone itself and another names it or a path under it."""
    out: list[str] = []
    for zone in unique_zones(shared):
        names_it = touches = 0
        for nid in leaf_ids:
            mine = zones.get(nid, [])
            names_it += any(zone_key(z) == zone_key(zone) for z in mine)
            touches += any(in_zone_tree(z, zone) for z in mine)
        if names_it and touches >= 2:
            out.append(zone)
    return out
