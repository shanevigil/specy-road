"""Touch zones checked against the files git tracks, when they are written.

The matcher (:func:`specy_road.finish_implementation_check.zone_matches`) reads a
zone as a file, a directory or a glob. A bare name prefix such as
``pkg/worker_ops_`` is none of those: it is read as a literal path, matches
nothing, and the executor whose real files are ``pkg/worker_ops_*.py`` stops for
files "outside its zones". Nothing said so while the zone was being written.

:func:`warn_untracked_zones` runs inside ``validate`` over every open node (Not
Started included, unlike :mod:`validate_touch_zones`, which reads the working
tree for started nodes only). Advisory, and silent when git cannot list the tree:

* a zone that is a name prefix of tracked files gets a stderr warning of its
  own naming the glob to use: tracked files extend it, so it is no file the work
  will create, and the line reaches ``add-node`` and ``edit-node`` too;
* every other zone that matches no tracked file and is not a directory, plain
  path or glob, is named in one stdout notice for all nodes, which says to keep
  a zone that names a file the work will create, so that nobody deletes one to
  silence it. A notice, like the unauthored-leaf block, because ``--strict``
  fails on any stderr line and a fresh ``init project`` scaffold names a file
  its first leaf will create; one line rather than one per node because the
  guidance is the same for all of them. It lists at most :data:`LISTED_LIMIT`
  nodes, claimed or In Progress first, and counts the rest by status: a Not
  Started unclaimed leaf is the usual case (the work will create the file), so
  it is only counted; ``validate --all`` lists every node.

:func:`warn_written_zones` is that second line as a stderr warning for the one
node ``add-node`` or ``edit-node --set touch_zones=`` just wrote: they print
only the stderr ``warning`` lines of the validation they run, so the notice
never reaches them.
"""

from __future__ import annotations

import bisect
import sys
from collections import Counter
from pathlib import Path, PurePosixPath

from specy_road.finish_implementation_check import zone_matches
from specy_road.git_subprocess import git_stdout
from specy_road.runtime_paths import git_root, project_prefix, rebase_to_project

_GLOB_CHARS = "*?["
_SETTLED = {"complete", "archived", "cancelled"}
#: How many nodes the untracked-zone notice names before it counts the rest by status.
LISTED_LIMIT = 10

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


def untracked_zones(zones: object, tracked: Tracked) -> list[str]:
    """Zones naming no tracked file and no directory, leaving out name prefixes."""
    if not isinstance(zones, list):
        return []
    out = []
    for z in zones:
        cleaned = _clean(z)
        if not cleaned:
            continue
        if Path(cleaned).is_absolute() or ".." in PurePosixPath(cleaned).parts:
            out.append(z)
        elif not tracked.matches(cleaned) and not prefix_of(z, tracked):
            out.append(z)
    return out


def _warn_prefix(nid: str, zone: str, extends: list[str]) -> None:
    print(
        f"roadmap: warning — {nid} touch zone {zone!r} is a name prefix of "
        f"{len(extends)} tracked file(s) (e.g. {extends[0]!r}) and matches none of "
        f"them: {GLOB_HINT}. Use {_glob_for(zone, extends)!r} "
        f"(specy-road edit-node {nid} --set touch_zones=<paths>).",
        file=sys.stderr,
    )


def _untracked_line(entries: list[str], hidden: str = "") -> str:
    listed = "; ".join(entries) + (f"; and {hidden}" if entries and hidden else hidden)
    return (
        "touch zones that match no tracked file and are not a directory: "
        f"{listed}. Keep a zone that names a file the work will create; "
        "otherwise fix the path (specy-road edit-node <NODE_ID> --set "
        f"touch_zones=<paths>) — {GLOB_HINT}."
    )


def _entry(nid: str, zones: list[str]) -> str:
    return f"{nid} " + ", ".join(repr(z) for z in zones)


def _status(node: dict) -> str:
    status = node.get("status")
    return status.strip() if isinstance(status, str) and status.strip() else "Not Started"


def _rank(node: dict, claimed: set[str], parents: set[str]) -> int:
    """0 claimed or In Progress, 1 any other status, 2 Not Started, 3 Not Started unclaimed leaf (counted only)."""
    nid, status = str(node.get("id", "?")), _status(node).lower()
    if nid in claimed or status == "in progress":
        return 0
    if status != "not started":
        return 1
    return 2 if nid in parents else 3


def _hidden(nodes: list[dict], *, more: bool) -> str:
    """``N [more] node(s) (by status: …); …`` for the nodes the notice counts instead of naming."""
    if not nodes:
        return ""
    counts = Counter(_status(n) for n in nodes)
    by_status = ", ".join(f"{status} {n}" for status, n in sorted(counts.items()))
    return (f"{len(nodes)}{' more' if more else ''} node(s) (by status: {by_status}); "
            "`specy-road validate --all` lists every one")


def warn_untracked_zones(
    nodes: list[dict],
    project_root: Path,
    *,
    claims: list[dict] | None = None,
    show_all: bool = False,
) -> None:
    """``validate``: open nodes' zones that match no tracked file and are not a directory.

    ``claims`` are the registry entries ``validate`` already loaded. Unless
    ``show_all``, at most :data:`LISTED_LIMIT` nodes are named, in :func:`_rank`
    order, and Not Started unclaimed leaves are never named, only counted.
    """
    open_nodes = [
        n for n in nodes
        if isinstance(n.get("touch_zones"), list) and n["touch_zones"] and not _is_settled(n)
    ]
    tracked = tracked_files(project_root) if open_nodes else None
    if tracked is None:
        return
    claimed = {str(e.get("node_id")) for e in claims or [] if isinstance(e, dict)}
    parents = {str(n.get("parent_id")) for n in nodes if n.get("parent_id")}
    missing: list[tuple[int, int, dict, str]] = []
    for i, n in enumerate(open_nodes):
        nid = str(n.get("id", "?"))
        for z in n["touch_zones"]:
            extends = prefix_of(z, tracked) if isinstance(z, str) else []
            if extends:
                _warn_prefix(nid, z, extends)
        zones = untracked_zones(n["touch_zones"], tracked)
        if zones:
            missing.append((_rank(n, claimed, parents), i, n, _entry(nid, zones)))
    if not missing:
        return
    missing.sort(key=lambda m: m[:2])
    if show_all:
        listed, hidden = [m[3] for m in missing], []
    else:
        nameable = [m for m in missing if m[0] < 3]
        listed = [m[3] for m in nameable[:LISTED_LIMIT]]
        hidden = [m[2] for m in nameable[LISTED_LIMIT:]] + [m[2] for m in missing if m[0] == 3]
    line = _untracked_line(listed, _hidden(hidden, more=bool(listed)))
    print(f"roadmap: notice — {line}")   # stdout: --strict does not count it


def warn_written_zones(node_id: str, zones: object, project_root: Path) -> None:
    """``add-node`` / ``edit-node``: the written node's untracked zones, as a stderr warning."""
    tracked = tracked_files(project_root) if isinstance(zones, list) and zones else None
    missing = untracked_zones(zones, tracked) if tracked is not None else []
    if missing:
        print(f"roadmap: warning — {_untracked_line([_entry(node_id, missing)])}", file=sys.stderr)
