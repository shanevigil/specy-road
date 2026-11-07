"""Warn when a node's ``touch_zones`` name nothing that exists on disk.

Touch zones are free text: the PM authors them at planning time, often before
the code they point at is written, and nothing has ever checked them against the
working tree. A zone naming a file that does not exist survives all the way to
the implementing agent, where the brief's "confirm touch zones" TODO is the first
thing to catch it. This is the authoring-time catch for the same mistake.

Non-fatal on purpose, and silent for nodes that have not started: their zones
name the files the work will create, so "matches nothing" is the expected state.
Reporting them taught agents to "fix" the warning by deleting those zones,
which is the opposite of what the check is for. It reports In Progress and Blocked nodes, where a zone
that matches nothing is more likely a typo or a path that moved.

:func:`notice_stale_sheet_zones` is the exception, for every status: a literal
zone naming a planning sheet that is not in the working tree names a sheet a
move renamed, not a file the work will create. A stdout notice, which
``validate --strict`` does not count.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from specy_road.runtime_paths import prefix_within

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


def _not_started(node: dict) -> bool:
    value = node.get("rollup_status") or node.get("status")
    return isinstance(value, str) and value.strip().lower() == "not started"


def _is_settled(node: dict) -> bool:
    for key in ("rollup_status", "status"):
        value = node.get(key)
        if isinstance(value, str) and value.strip().lower() in _SETTLED:
            return True
    return False


def _zone_matches_either_root(project_root: Path, git_root: Path | None, zone: str) -> bool:
    """Whether ``zone`` exists when read from the project root or the git root."""
    if _zone_matches(project_root, zone):
        return True
    if git_root is not None and git_root != project_root and _zone_matches(git_root, zone):
        return True
    return False


def _missing_zones(
    nodes: list[dict], project_root: Path, git_root: Path | None
) -> list[tuple[str, list[str]]]:
    out: list[tuple[str, list[str]]] = []
    for node in nodes:
        zones = node.get("touch_zones")
        if not isinstance(zones, list) or not zones or _is_settled(node) or _not_started(node):
            continue
        missing = [
            z for z in zones
            if isinstance(z, str)
            and not _zone_matches_either_root(project_root, git_root, z)
        ]
        if missing:
            out.append((str(node.get("id", "?")), missing))
    return out


def warn_touch_zones_match_nothing(
    nodes: list[dict], project_root: Path, *, git_root: Path | None = None
) -> None:
    """One non-fatal block naming every open node whose zones match nothing.

    Reported as a single block rather than a self-contained warning per node.
    This runs inside every ``validate``, which runs inside every pickup, every
    node edit and every finish — and the per-node form repeated the same two
    sentences of guidance each time, so a roadmap with five drifted nodes put
    nineteen lines in front of an operator on every command. The guidance is
    identical for all of them, so it is printed once, at the end.
    """
    missing = _missing_zones(nodes, project_root, git_root)
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
        "  Zones are paths or globs relative to the project root or the git root "
        "(for example ``specy_road/`` beside a nested ``sr/`` project), and may "
        "name files the work will still create.\n"
        "  Correct only a typo or a path that moved (specy-road edit-node <NODE_ID> "
        "--set touch_zones=<paths>); do not remove zones just to silence this.",
        file=sys.stderr,
    )


#: A sheet file name ends in ``_<node_key>.md``.
_SHEET_KEY = re.compile(r"_([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\.md$", re.I)


def _sheet_rel(zone: str, prefix: str) -> tuple[str, str] | None:
    """``(planning/<file>.md, form prefix)`` when a literal ``zone`` names a sheet, else ``None``.

    One rule for both forms: the zone is read as project-relative first, and
    only when that reading is no sheet path, with the checkout ``prefix``
    stripped. So a project directory itself named ``planning`` keeps
    ``planning/<file>.md`` as a project-form zone.
    """
    if any(c in zone for c in _GLOB_CHARS):
        return None
    for form in dict.fromkeys(("", prefix)):
        rel = zone[len(form):]
        head, _, name = rel.partition("/")
        if zone.startswith(form) and head == "planning" and name.endswith(".md") and "/" not in name:
            return rel, form
    return None


def _sheet_exists(project_root: Path, rel: str) -> bool:
    try:
        return (project_root / rel).exists()
    except (ValueError, OSError):
        return True  # cannot tell reads as present, as in _zone_matches


def notice_stale_sheet_zones(
    nodes: list[dict], project_root: Path, *, git_root: Path | None = None
) -> None:
    """One stdout notice line per literal zone naming a planning sheet that does not exist.

    Any status, either form (``planning/<file>.md`` or, for a nested project,
    ``sr/planning/<file>.md``), working-tree existence so an unstaged rename
    counts. When the file name ends in a live node's ``_<node_key>.md``, the
    line names that node's current sheet as the likely fix.
    """
    prefix = prefix_within(git_root, project_root) if git_root is not None else ""
    by_key = {n.get("node_key"): n for n in nodes if isinstance(n.get("planning_dir"), str)}
    for node in nodes:
        zones = node.get("touch_zones")
        for zone in zones if isinstance(zones, list) else []:
            found = _sheet_rel(zone.strip(), prefix) if isinstance(zone, str) else None
            if found is None or _sheet_exists(project_root, found[0]):
                continue
            rel, form = found
            nid = node.get("id", "?")
            line = f"roadmap: notice — {nid}: touch zone {zone!r} names a planning sheet that does not exist"
            key = _SHEET_KEY.search(rel)
            owner = by_key.get(key.group(1).lower()) if key else None
            if owner is not None:
                now = form + owner["planning_dir"]
                line += f"; {owner.get('id', '?')}'s sheet is now {now!r} (specy-road edit-node {nid} --set touch_zones=<paths>)"
            print(line)
