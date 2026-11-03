"""Registry touch-zone overlap warnings for validate and roadmap CRUD."""

from __future__ import annotations

import contextlib
import sys
from contextvars import ContextVar

_authoring_overlap_scope: ContextVar[tuple[str, list[str]] | None] = ContextVar(
    "authoring_overlap_scope", default=None
)


@contextlib.contextmanager
def authoring_overlap_scope(label: str, touch_zones: list[str]):
    """Limit registry overlap warnings to clashes with one node's touch zones."""
    token = _authoring_overlap_scope.set((label, list(touch_zones)))
    try:
        yield
    finally:
        _authoring_overlap_scope.reset(token)


@contextlib.contextmanager
def authoring_overlap_for_node(node: dict, *, node_id: str | None = None):
    """``authoring_overlap_scope`` for a roadmap node dict (add-node / edit-node)."""
    nid = node_id or str(node.get("id") or "?")
    label = str(node.get("codename") or nid)
    with authoring_overlap_scope(label, list(node.get("touch_zones") or [])):
        yield


def current_authoring_overlap_scope() -> tuple[str, list[str]] | None:
    return _authoring_overlap_scope.get()


def _touch_zones_clash(x: str, y: str) -> bool:
    y_base = y.rstrip("/")
    x_base = x.rstrip("/")
    nested = x.startswith(y_base + "/") or y.startswith(x_base + "/")
    return x == y or nested


def _is_broad_touch_zone(zone: str) -> bool:
    return zone.endswith("/")


def _first_touch_zone_clash(
    za: list[str], zb: list[str], *, skip: set[tuple[str, str]] | None = None
) -> tuple[str, str] | None:
    skip = skip or set()
    for x in za:
        for y in zb:
            if (x, y) in skip:
                continue
            if _touch_zones_clash(x, y):
                return x, y
    return None


def _broad_zone_summaries(entries: list[dict]) -> list[tuple[str, list[str]]]:
    by_zone: dict[str, set[str]] = {}
    for entry in entries:
        cn = entry.get("codename") or "?"
        for zone in entry.get("touch_zones") or []:
            if _is_broad_touch_zone(zone):
                by_zone.setdefault(zone, set()).add(cn)
    return sorted(
        (zone, sorted(cns))
        for zone, cns in by_zone.items()
        if len(cns) >= 2
    )


def touch_zone_overlap(
    entries: list[dict],
    *,
    scope_label: str | None = None,
    scope_touch_zones: list[str] | None = None,
) -> None:
    """Warn if entries share a touch zone path (heuristic).

    With ``scope_touch_zones``, only warn for registry claims that clash with
    that node (add-node / edit-node). Otherwise list all clashes: broad shared
    zones once per zone, other claim pairs one line each.
    """
    if scope_touch_zones is not None:
        label = scope_label or "?"
        scoped = sorted(scope_touch_zones)
        for entry in entries:
            zb = sorted(entry.get("touch_zones") or [])
            clash = _first_touch_zone_clash(scoped, zb)
            if clash is None:
                continue
            x, y = clash
            bc = entry.get("codename")
            print(
                f"registry: warning — possible overlap '{x}' vs "
                f"'{y}' ({label} vs {bc})",
                file=sys.stderr,
            )
        return

    skip_clashes: set[tuple[str, str]] = set()
    for zone, cns in _broad_zone_summaries(entries):
        skip_clashes.add((zone, zone))
        joined = ", ".join(cns)
        print(
            f"registry: warning — possible overlap on shared zone "
            f"{zone!r} (claims: {joined})",
            file=sys.stderr,
        )

    for i, a in enumerate(entries):
        za = sorted(a.get("touch_zones") or [])
        ac = a.get("codename") or "?"
        for j in range(i + 1, len(entries)):
            b = entries[j]
            zb = sorted(b.get("touch_zones") or [])
            bc = b.get("codename") or "?"
            clash = _first_touch_zone_clash(za, zb, skip=skip_clashes)
            if clash is None:
                continue
            x, y = clash
            print(
                f"registry: warning — possible overlap '{x}' vs "
                f"'{y}' ({ac} vs {bc})",
                file=sys.stderr,
            )


def warn_registry_touch_zone_overlap(
    entries: list[dict],
    *,
    no_overlap_warn: bool,
    overlap_scope: tuple[str, list[str]] | None,
) -> None:
    if not entries or no_overlap_warn:
        return
    if overlap_scope is not None:
        label, zones = overlap_scope
        touch_zone_overlap(entries, scope_label=label, scope_touch_zones=zones)
    else:
        touch_zone_overlap(entries)
