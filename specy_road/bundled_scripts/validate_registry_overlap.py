"""Registry touch-zone overlap warnings for validate and roadmap CRUD."""

from __future__ import annotations

import contextlib
import sys
from collections.abc import Iterable
from contextvars import ContextVar
from pathlib import Path
from typing import NamedTuple

from specy_road.shared_zones import (
    DEFAULT_SHARED_ZONES,
    in_zone_tree,
    is_shared_zone,
    norm_zone,
    resolve_shared_zones,
    zones_overlap,
)

AuthoringOverlapScope = NamedTuple(
    "AuthoringOverlapScope",
    [("label", str), ("node_id", str | None), ("touch_zones", list[str])],
)

_authoring_overlap_scope: ContextVar[AuthoringOverlapScope | None] = ContextVar(
    "authoring_overlap_scope", default=None
)


@contextlib.contextmanager
def authoring_overlap_scope(
    label: str, touch_zones: list[str], *, node_id: str | None = None
):
    """Limit registry overlap warnings to clashes with one node's touch zones."""
    token = _authoring_overlap_scope.set(
        AuthoringOverlapScope(label, node_id, list(touch_zones))
    )
    try:
        yield
    finally:
        _authoring_overlap_scope.reset(token)


@contextlib.contextmanager
def authoring_overlap_for_node(node: dict, *, node_id: str | None = None):
    """``authoring_overlap_scope`` for a roadmap node dict (add-node / edit-node)."""
    nid = node_id or str(node.get("id") or "?")
    label = str(node.get("codename") or nid)
    with authoring_overlap_scope(label, list(node.get("touch_zones") or []), node_id=nid):
        yield


def current_authoring_overlap_scope() -> AuthoringOverlapScope | None:
    return _authoring_overlap_scope.get()


def _is_broad_touch_zone(zone: str) -> bool:
    return zone.strip().endswith("/")


def _clash_suppressed_by_broad_summary(
    x: str, y: str, summarized_broad: set[str]
) -> bool:
    """True when the clash is already covered by a shared-directory summary."""
    if norm_zone(x) == norm_zone(y) and not _is_broad_touch_zone(x):
        return False
    for zone in summarized_broad:
        if in_zone_tree(x, zone) and in_zone_tree(y, zone):
            return True
    return False


def _first_independent_pair_clash(
    za: list[str], zb: list[str], *, summarized_broad: set[str], shared: Iterable[str]
) -> tuple[str, str] | None:
    for x in za:
        for y in zb:
            if not zones_overlap(x, y, shared):
                continue
            if _clash_suppressed_by_broad_summary(x, y, summarized_broad):
                continue
            return x, y
    return None


def _first_touch_zone_clash(
    za: list[str], zb: list[str], shared: Iterable[str]
) -> tuple[str, str] | None:
    for x in za:
        for y in zb:
            if zones_overlap(x, y, shared):
                return x, y
    return None


def _claimsin_zone_tree(entries: list[dict], zone: str) -> set[str]:
    names: set[str] = set()
    for entry in entries:
        cn = entry.get("codename") or "?"
        for path in entry.get("touch_zones") or []:
            if in_zone_tree(path, zone):
                names.add(cn)
                break
    return names


def _broad_zone_summaries(
    entries: list[dict], shared: Iterable[str]
) -> list[tuple[str, list[str]]]:
    exact: dict[str, set[str]] = {}
    for entry in entries:
        cn = entry.get("codename") or "?"
        for zone in entry.get("touch_zones") or []:
            if _is_broad_touch_zone(zone) and not is_shared_zone(zone, shared):
                exact.setdefault(norm_zone(zone), set()).add(cn)
    return sorted(
        (zone, sorted(_claimsin_zone_tree(entries, zone)))
        for zone, owners in exact.items()
        if len(owners) >= 2
    )


def touch_zone_overlap(
    entries: list[dict],
    *,
    scope_label: str | None = None,
    scope_touch_zones: list[str] | None = None,
    scope_node_id: str | None = None,
    shared: Iterable[str] = DEFAULT_SHARED_ZONES,
) -> None:
    """Warn if entries share a touch zone path (heuristic).

    With ``scope_touch_zones``, only warn for registry claims that clash with
    that node (add-node / edit-node). Otherwise list all clashes: broad shared
    zones once per zone, other claim pairs one line each. A clash where one
    zone is itself one of ``shared`` (``grind.shared_zones``) is not reported,
    the rule ``grind-session --plan`` batches by.
    """
    shared = tuple(shared)
    if scope_touch_zones is not None:
        label = scope_label or "?"
        scoped = sorted(scope_touch_zones)
        for entry in entries:
            if scope_node_id and entry.get("node_id") == scope_node_id:
                continue
            zb = sorted(entry.get("touch_zones") or [])
            clash = _first_touch_zone_clash(scoped, zb, shared)
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

    summaries = _broad_zone_summaries(entries, shared)
    summarized_broad = {zone for zone, _ in summaries}
    for zone, cns in summaries:
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
            clash = _first_independent_pair_clash(
                za, zb, summarized_broad=summarized_broad, shared=shared
            )
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
    overlap_scope: AuthoringOverlapScope | None,
    repo_root: Path | None = None,
) -> None:
    if not entries or no_overlap_warn:
        return
    shared = resolve_shared_zones(repo_root) if repo_root else DEFAULT_SHARED_ZONES
    if overlap_scope is not None:
        touch_zone_overlap(
            entries,
            scope_label=overlap_scope.label,
            scope_touch_zones=overlap_scope.touch_zones,
            scope_node_id=overlap_scope.node_id,
            shared=shared,
        )
    else:
        touch_zone_overlap(entries, shared=shared)
