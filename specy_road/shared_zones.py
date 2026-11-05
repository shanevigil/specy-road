"""Shared documentation zones: directory touch zones that do not make leaves overlap.

Almost every leaf names ``planning/`` and ``shared/`` in its touch zones, so the
plain overlap rule (same path, or one a directory prefix of the other) put every
ready leaf in its own ``grind-session --plan`` batch. A configured shared zone,
named as a zone itself, overlaps nothing; two leaves naming the same file (or the
same subdirectory) under it still overlap. Configured with ``grind.shared_zones``
in ``roadmap/git-workflow.yaml`` (schema-checked); an empty list turns it off.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from specy_road.git_workflow_config import load_git_workflow_config

DEFAULT_SHARED_ZONES: tuple[str, ...] = ("planning/", "shared/")


def norm_zone(zone: str) -> str:
    return zone.strip().removeprefix("./").rstrip("/")


def resolve_shared_zones(repo_root: Path) -> tuple[str, ...]:
    """``grind.shared_zones`` from ``roadmap/git-workflow.yaml``, else the default.

    An unreadable config yields the default, as the other git-workflow settings do.
    """
    data, err = load_git_workflow_config(repo_root)
    zones = ((data or {}).get("grind") or {}).get("shared_zones") if not err else None
    return DEFAULT_SHARED_ZONES if zones is None else tuple(zones)


def paths_overlap(a: str, b: str) -> bool:
    """The same path, or one a directory prefix of the other."""
    x, y = norm_zone(a), norm_zone(b)
    return x == y or x.startswith(y + "/") or y.startswith(x + "/")


def shared_ignores(a: str, b: str, shared: Iterable[str]) -> bool:
    """True when ``a`` or ``b`` is itself a shared zone, so their overlap does not count."""
    names = {norm_zone(z) for z in shared}
    return norm_zone(a) in names or norm_zone(b) in names


def effective_overlap(
    a_zones: Iterable[str], b_zones: Iterable[str], shared: Iterable[str]
) -> tuple[str, str] | None:
    """First ``(a zone, b zone)`` pair that overlaps once shared zones are ignored."""
    shared = tuple(shared)
    b_zones = list(b_zones)
    for a in a_zones:
        for b in b_zones:
            if paths_overlap(a, b) and not shared_ignores(a, b, shared):
                return a, b
    return None


def ignored_shared_zones(
    zones: dict[str, list[str]], leaf_ids: Iterable[str], shared: Iterable[str]
) -> list[str]:
    """Shared zones that would have held a leaf back: one of ``leaf_ids`` names the
    zone itself and another names it or a path under it."""
    out: list[str] = []
    for zone in shared:
        base = norm_zone(zone)
        names_it = touches = 0
        for nid in leaf_ids:
            mine = [norm_zone(z) for z in zones.get(nid, [])]
            names_it += base in mine
            touches += any(z == base or z.startswith(base + "/") for z in mine)
        if names_it and touches >= 2:
            out.append(zone)
    return out
