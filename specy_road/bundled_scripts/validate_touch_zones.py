"""Warn when a node's ``touch_zones`` name nothing that exists on disk.

Touch zones are free text: the PM authors them at planning time, often before
the code they point at is written, and nothing has ever checked them against the
working tree. A zone naming a file that does not exist survives all the way to
the implementing agent, where the brief's "confirm touch zones" TODO is the first
thing to catch it. This is the authoring-time catch for the same mistake.

Non-fatal on purpose. A zone that is genuinely ahead of the code is legitimate
for work that has not started, and the overlap heuristic next door is advisory
for the same reason.
"""

from __future__ import annotations

import sys
from pathlib import Path

#: Glob metacharacters. A zone containing one is matched with ``Path.glob``.
_GLOB_CHARS = "*?["

#: Statuses whose zones are already history — the work landed, and a zone that
#: pointed at a file since renamed is not a mistake anyone should act on.
_SETTLED = {"complete", "archived", "cancelled"}


def _zone_matches(root: Path, zone: str) -> bool:
    """Whether ``zone`` names anything under ``root``, as a path or a glob."""
    cleaned = zone.strip().rstrip("/")
    if not cleaned:
        return True  # an empty zone is a different problem; not ours to report
    candidate = Path(cleaned)
    if candidate.is_absolute() or ".." in candidate.parts:
        return False
    if any(c in cleaned for c in _GLOB_CHARS):
        try:
            return any(root.glob(cleaned))
        except (ValueError, OSError):
            return False
    return (root / candidate).exists()


def _is_settled(node: dict) -> bool:
    for key in ("rollup_status", "status"):
        value = node.get(key)
        if isinstance(value, str) and value.strip().lower() in _SETTLED:
            return True
    return False


def warn_touch_zones_match_nothing(nodes: list[dict], root: Path) -> None:
    """One non-fatal line per open node whose touch zone matches nothing."""
    for node in nodes:
        zones = node.get("touch_zones")
        if not isinstance(zones, list) or not zones:
            continue
        if _is_settled(node):
            continue
        missing = [
            z for z in zones
            if isinstance(z, str) and not _zone_matches(root, z)
        ]
        if not missing:
            continue
        nid = node.get("id", "?")
        listed = ", ".join(repr(z) for z in missing)
        label = "touch zone" if len(missing) == 1 else "touch zones"
        verb = "matches" if len(missing) == 1 else "match"
        print(
            f"roadmap: warning — {nid} {label} {listed} {verb} nothing in the "
            "working tree. Zones are paths or globs relative to the project "
            f"root. Run: specy-road edit-node {nid} --set touch_zones=<paths>",
            file=sys.stderr,
        )
