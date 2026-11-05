"""Plan-time check: acceptance criteria that name repo paths the leaf's zones do not cover.

**Path candidates (best-effort, false negatives accepted).** A token is considered
only when it contains ``/`` or ends in a known file suffix (``.py``, ``.md``,
``.json``, ``.yaml``, ``.yml``, ``.toml``, ``.ts``, ``.tsx``, ``.sh``, ``.txt``,
``.cfg``, ``.ini``), and either:

* it appears in backticks, or
* it is a bare word that starts with a top-level directory name from ``git ls-tree``
  at ``ref`` or ends in one of those suffixes.

Prose such as ``input/output`` or ``M12/M13`` is ignored unless it meets that rule.
An existing candidate is a tracked blob or a directory prefix of one. A missing
candidate adds :data:`NEW_OUTSIDE` only when it has a known suffix or its parent
directory already contains tracked files. Compared to touch zones via
:func:`specy_road.finish_implementation_check.in_zones`. Used by ``orchestrate plan``
and ``grind-session --plan``.
"""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath
from typing import Iterable

from specy_road.finish_implementation_check import in_zones
from specy_road.git_subprocess import git_stdout
from specy_road.runtime_paths import project_prefix, rebase_to_project

NEW_OUTSIDE = "new file outside zones"
BEST_EFFORT_HINT = (
    "best-effort path detection (backticks, bare tokens under a tracked top-level "
    "dir or with a known suffix only; other slash phrases are ignored)"
)
_BACKTICK = re.compile(r"`([^`]+)`")
_SLASH_TOKEN = re.compile(r"(?<![\w./-])([A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+)(?![\w./-])")
_KNOWN_SUFFIXES = (
    ".py", ".md", ".json", ".yaml", ".yml", ".toml", ".ts", ".tsx", ".sh", ".txt", ".cfg", ".ini",
)


def _acceptance(node: dict) -> list[str]:
    raw = node.get("acceptance") or []
    return [a.strip() for a in raw if isinstance(a, str) and a.strip()]


def _zones(node: dict) -> list[str]:
    return [z.strip().strip("/") for z in (node.get("touch_zones") or []) if isinstance(z, str) and z.strip()]


def _normalize(token: str) -> tuple[str, bool] | None:
    raw = token.strip()
    t = raw.strip(".,;:)\"'")
    if not t or t.startswith(("http://", "https://", "-", "/")) or ".." in t.split("/"):
        return None
    had_slash = t.endswith("/")
    norm = t.removeprefix("./").rstrip("/") or None
    if not norm:
        return None
    return norm, had_slash


def _has_known_suffix(path: str) -> bool:
    return PurePosixPath(path).suffix.lower() in _KNOWN_SUFFIXES


def _shape_ok(path: str, *, had_slash: bool, backtick: bool, top_dirs: set[str]) -> bool:
    if had_slash or "/" in path or _has_known_suffix(path):
        return True
    return backtick and path in top_dirs


def _top_level_dirs(tracked: set[str]) -> set[str]:
    return {p.split("/", 1)[0] for p in tracked if p}


def _path_forms(path: str, prefix: str) -> set[str]:
    forms = {path}
    if prefix:
        forms.add(f"{prefix}{path}")
        rebased = rebase_to_project(path, prefix)
        if rebased:
            forms.add(rebased)
    return forms


def _exists(path: str, tracked: set[str], prefix: str) -> bool:
    """True when ``path`` is a tracked blob or a directory prefix of one."""
    for form in _path_forms(path, prefix):
        if form in tracked:
            return True
        head = f"{form}/"
        if any(p.startswith(head) for p in tracked):
            return True
    return False


def _path_candidate(
    path: str, *, had_slash: bool, backtick: bool, top_dirs: set[str],
) -> bool:
    if not _shape_ok(path, had_slash=had_slash, backtick=backtick, top_dirs=top_dirs):
        return False
    if backtick:
        return True
    head = path.split("/", 1)[0]
    return head in top_dirs or _has_known_suffix(path)


def _report_as_new(path: str, tracked: set[str], prefix: str) -> bool:
    if _has_known_suffix(path):
        return True
    parent = PurePosixPath(path).parent
    if str(parent) in (".", ""):
        return False
    return _exists(str(parent), tracked, prefix)


def _tokens(line: str) -> list[tuple[str, bool, bool]]:
    seen: set[str] = set()
    out: list[tuple[str, bool, bool]] = []
    for raw in _BACKTICK.findall(line):
        parsed = _normalize(raw)
        if parsed and parsed[0] not in seen:
            seen.add(parsed[0])
            out.append((parsed[0], True, parsed[1]))
    scrub = _BACKTICK.sub(" ", line)
    for raw in _SLASH_TOKEN.findall(scrub):
        parsed = _normalize(raw)
        if parsed and parsed[0] not in seen:
            seen.add(parsed[0])
            out.append((parsed[0], False, parsed[1]))
    return out


def _tracked_paths(root: Path, ref: str) -> set[str] | None:
    out = git_stdout(["ls-tree", "-r", "--full-tree", "-z", ref], root)
    if out is None:
        return None
    paths: set[str] = set()
    for rec in filter(None, out.split("\0")):
        _, path = rec.split("\t", 1)
        paths.add(path)
    return paths


def _label_for_candidate(
    path: str,
    *,
    zones: list[str],
    prefix: str,
    tree: set[str],
    labels: list[str],
) -> bool:
    """Append an uncovered label when needed; return whether to set ``new_outside``."""
    if in_zones(zones, path, prefix):
        return False
    if _exists(path, tree, prefix):
        if path not in labels:
            labels.append(path)
        return False
    return _report_as_new(path, tree, prefix)


def uncovered_acceptance_paths(
    root: Path,
    node: dict,
    *,
    ref: str = "HEAD",
    tracked: set[str] | None = None,
) -> list[str]:
    """Labels for path candidates acceptance names that no touch zone covers."""
    zones = _zones(node)
    lines = _acceptance(node)
    if not lines:
        return []
    prefix = project_prefix(root)
    tree = tracked if tracked is not None else _tracked_paths(root, ref)
    if tree is None:
        return []
    top_dirs = _top_level_dirs(tree)
    labels: list[str] = []
    new_outside = False
    for line in lines:
        for path, backtick, had_slash in _tokens(line):
            if not _path_candidate(path, had_slash=had_slash, backtick=backtick, top_dirs=top_dirs):
                continue
            if _label_for_candidate(path, zones=zones, prefix=prefix, tree=tree, labels=labels):
                new_outside = True
    if new_outside and NEW_OUTSIDE not in labels:
        labels.append(NEW_OUTSIDE)
    return labels


def leaf_zone_coverage_warning(node_id: str, labels: list[str]) -> str:
    return (
        f"{node_id}: acceptance names paths outside touch zones ({BEST_EFFORT_HINT}): "
        + ", ".join(labels)
    )


def zone_coverage_warnings(
    root: Path,
    by_id: dict[str, dict],
    node_ids: Iterable[str],
    *,
    ref: str = "HEAD",
) -> dict[str, str]:
    """``node_id -> one warning line`` for leaves with uncovered acceptance paths."""
    tracked = _tracked_paths(root, ref)
    if tracked is None:
        return {}
    out: dict[str, str] = {}
    for nid in node_ids:
        node = by_id.get(nid)
        if not node:
            continue
        labels = uncovered_acceptance_paths(root, node, ref=ref, tracked=tracked)
        if labels:
            out[nid] = leaf_zone_coverage_warning(nid, labels)
    return out
