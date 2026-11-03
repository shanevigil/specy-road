"""Touch zones checked against the files git tracks, when they are written.

The matcher (:func:`specy_road.finish_implementation_check.zone_matches`) reads a
zone as a file, a directory or a glob. A bare name prefix such as
``pkg/worker_ops_`` is none of those: it is read as a literal path, matches
nothing, and the executor whose real files are ``pkg/worker_ops_*.py`` stops for
files "outside its zones". Nothing said so while the zone was being written.

Two checks, both advisory and both silent when git cannot list the tree:

* :func:`warn_zone_prefixes` runs inside ``validate`` (so inside every
  ``add-node`` and ``edit-node`` too) and names an open node's zone that is a
  name prefix of tracked files but no file or directory itself. It covers Not
  Started nodes, unlike :mod:`validate_touch_zones`: a zone that tracked files
  extend is not a file the work will create.
* :func:`warn_untracked_zones` runs once, for the node ``add-node`` or
  ``edit-node --set touch_zones=`` just wrote, and names every other zone that
  matches no tracked file and is not a directory. A new file is a fine zone; the
  warning says so, so that nobody deletes one to silence it.

Each warning is one line containing ``warning``, because ``add-node`` and
``edit-node`` re-print only such lines from the validation they run.
"""

from __future__ import annotations

import bisect
import sys
from pathlib import Path, PurePosixPath

from specy_road.finish_implementation_check import zone_matches
from specy_road.git_subprocess import git_stdout
from specy_road.runtime_paths import git_root, project_prefix, rebase_to_project

_GLOB_CHARS = "*?["
_SETTLED = {"complete", "archived", "cancelled"}

GLOB_HINT = (
    "zones are paths, directories or globs (for example 'pkg/worker_ops_*.py'); "
    "a bare name prefix is read as a literal path and is not supported"
)


class Tracked:
    """Every tracked file, in its git-root form and, under the project, its project form."""

    def __init__(self, paths: set[str], roots: tuple[Path, ...]) -> None:
        self.ordered = sorted(paths)
        self.roots = roots

    def starting_with(self, text: str) -> list[str]:
        """Tracked paths that begin with ``text``, in order."""
        i, out = bisect.bisect_left(self.ordered, text), []
        while i < len(self.ordered) and self.ordered[i].startswith(text):
            out.append(self.ordered[i])
            i += 1
        return out

    def matches(self, zone: str) -> bool:
        """Whether ``zone`` names a tracked file, or a directory tracked or on disk."""
        if any(c in zone for c in _GLOB_CHARS):
            return any(zone_matches(zone, p) for p in self.ordered)
        i = bisect.bisect_left(self.ordered, zone)
        if i < len(self.ordered) and self.ordered[i] == zone:
            return True
        if self.starting_with(f"{zone}/")[:1]:
            return True
        try:
            return any((r / zone).is_dir() for r in self.roots)
        except (ValueError, OSError):
            return True   # cannot tell; an advisory check must not fail a write


def tracked_files(project_root: Path) -> Tracked | None:
    """What ``git ls-files`` lists for the whole repo, or ``None`` outside git."""
    top = git_root(project_root)
    if top is None:
        return None
    out = git_stdout(["ls-files", "-z"], top)
    if out is None:
        return None
    prefix = project_prefix(project_root)
    paths: set[str] = set()
    for p in filter(None, out.split("\0")):
        paths.add(p)
        rebased = rebase_to_project(p, prefix)
        if rebased:
            paths.add(rebased)
    return Tracked(paths, (project_root, top))


def _clean(zone: object) -> str:
    return zone.strip().rstrip("/") if isinstance(zone, str) else ""


def prefix_of(zone: str, tracked: Tracked) -> list[str]:
    """Tracked files ``zone`` is only a name prefix of; empty when it names something.

    A zone ending in ``/`` says "directory" and is never read as a prefix.
    """
    cleaned = _clean(zone)
    if not cleaned or zone.strip().endswith("/") or any(c in cleaned for c in _GLOB_CHARS):
        return []
    if tracked.matches(cleaned):
        return []
    return tracked.starting_with(cleaned)


def _glob_for(zone: str, extends: list[str]) -> str:
    """``zone*``, with the extension when every file it prefixes shares one."""
    suffixes = {PurePosixPath(p).suffix for p in extends}
    ext = suffixes.pop() if len(suffixes) == 1 else ""
    return f"{_clean(zone)}*{ext}"


def _is_settled(node: dict) -> bool:
    return any(
        isinstance(node.get(k), str) and node[k].strip().lower() in _SETTLED
        for k in ("rollup_status", "status")
    )


def warn_zone_prefixes(nodes: list[dict], project_root: Path) -> None:
    """One line per open node's zone that is a name prefix of tracked files."""
    open_zones = [
        (str(n.get("id", "?")), z)
        for n in nodes
        if isinstance(n.get("touch_zones"), list) and not _is_settled(n)
        for z in n["touch_zones"]
        if _clean(z)
    ]
    if not open_zones:
        return
    tracked = tracked_files(project_root)
    if tracked is None:
        return
    for nid, zone in open_zones:
        extends = prefix_of(zone, tracked)
        if not extends:
            continue
        print(
            f"roadmap: warning — {nid} touch zone {zone!r} is a name prefix of "
            f"{len(extends)} tracked file(s) (e.g. {extends[0]!r}) and matches none of "
            f"them: {GLOB_HINT}. Use {_glob_for(zone, extends)!r} "
            f"(specy-road edit-node {nid} --set touch_zones=<paths>).",
            file=sys.stderr,
        )


def untracked_zones(zones: object, project_root: Path) -> list[str]:
    """Zones naming no tracked file and no directory, leaving out name prefixes.

    Prefixes are left to :func:`warn_zone_prefixes`, which ``validate`` prints
    for the same write with a glob to use instead.
    """
    if not isinstance(zones, list):
        return []
    wanted = [z for z in zones if _clean(z)]
    tracked = tracked_files(project_root) if wanted else None
    if tracked is None:
        return []
    out = []
    for z in wanted:
        cleaned = _clean(z)
        if Path(cleaned).is_absolute() or ".." in PurePosixPath(cleaned).parts:
            out.append(z)
        elif not tracked.matches(cleaned) and not prefix_of(z, tracked):
            out.append(z)
    return out


def warn_untracked_zones(node_id: str, zones: object, project_root: Path) -> None:
    """``add-node`` / ``edit-node``: one line naming the written node's untracked zones."""
    missing = untracked_zones(zones, project_root)
    if not missing:
        return
    print(
        f"roadmap: warning — {node_id} touch zone(s) match no tracked file and are not "
        f"a directory: {', '.join(repr(z) for z in missing)}. Keep a zone that names a "
        f"file this work will create; otherwise fix the path — {GLOB_HINT}.",
        file=sys.stderr,
    )
