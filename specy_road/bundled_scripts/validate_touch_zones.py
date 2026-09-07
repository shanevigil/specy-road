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


def _glob_is_bounded(root: Path, pattern: str) -> bool:
    """Whether this pattern can be matched without walking the whole tree.

    ``Path.glob`` is not ignore-aware, so an unmatched ``**`` walks `.git/`,
    `node_modules/` and every virtualenv — about a second per zone here, and
    roughly five times that per extra ``**``. This check runs inside every
    ``validate``, which runs inside every pickup and every node edit, so an
    unbounded pattern is refused rather than timed.

    Bounded means: at most one ``**``, and a concrete existing directory before
    it to prune the walk. Anything else is treated as unverifiable — the check
    is advisory, and a missing warning beats a hung gate.
    """
    segments = pattern.split("/")
    recursive = [i for i, seg in enumerate(segments) if "**" in seg]
    if not recursive:
        return True  # plain wildcards stay within their own directory level
    if len(recursive) > 1:
        return False
    prefix = segments[: recursive[0]]
    if not prefix or any(seg in (".", "") for seg in prefix):
        return False
    if any(c in seg for seg in prefix for c in _GLOB_CHARS):
        return False
    return root.joinpath(*prefix).is_dir()


def _zone_matches(root: Path, zone: str) -> bool:
    """Whether ``zone`` names anything under ``root``, as a path or a glob.

    Any filesystem complaint means "cannot tell", and cannot-tell must read as a
    match: this is an advisory check that runs inside ``validate``, which runs
    inside every pickup and every node edit. A zone long enough to raise
    ``ENAMETOOLONG``, or under a directory we may not traverse, is not worth
    turning a gate into a traceback.
    """
    cleaned = zone.strip().rstrip("/")
    if not cleaned:
        return True  # an empty zone is a different problem; not ours to report
    try:
        candidate = Path(cleaned)
        if candidate.is_absolute() or ".." in candidate.parts:
            return False
        if any(c in cleaned for c in _GLOB_CHARS):
            if not _glob_is_bounded(root, cleaned):
                return True
            return any(root.glob(cleaned))
        return (root / candidate).exists()
    except (ValueError, OSError):
        return True


def _is_settled(node: dict) -> bool:
    for key in ("rollup_status", "status"):
        value = node.get(key)
        if isinstance(value, str) and value.strip().lower() in _SETTLED:
            return True
    return False


def _missing_zones(nodes: list[dict], root: Path) -> list[tuple[str, list[str]]]:
    out: list[tuple[str, list[str]]] = []
    for node in nodes:
        zones = node.get("touch_zones")
        if not isinstance(zones, list) or not zones or _is_settled(node):
            continue
        missing = [
            z for z in zones
            if isinstance(z, str) and not _zone_matches(root, z)
        ]
        if missing:
            out.append((str(node.get("id", "?")), missing))
    return out


def warn_touch_zones_match_nothing(nodes: list[dict], root: Path) -> None:
    """One non-fatal block naming every open node whose zones match nothing.

    Reported as a single block rather than a self-contained warning per node.
    This runs inside every ``validate``, which runs inside every pickup, every
    node edit and every finish — and the per-node form repeated the same two
    sentences of guidance each time, so a roadmap with five drifted nodes put
    nineteen lines in front of an operator on every command. The guidance is
    identical for all of them, so it is printed once, at the end.
    """
    missing = _missing_zones(nodes, root)
    if not missing:
        return
    count = len(missing)
    subject = "1 node has" if count == 1 else f"{count} nodes have"
    print(
        f"roadmap: warning — {subject} touch zones that match nothing in the "
        "working tree:",
        file=sys.stderr,
    )
    for nid, zones in missing:
        print(f"  {nid}: {', '.join(repr(z) for z in zones)}", file=sys.stderr)
    print(
        "  Zones are paths or globs relative to the project root. Fix one with: "
        "specy-road edit-node <NODE_ID> --set touch_zones=<paths>",
        file=sys.stderr,
    )
