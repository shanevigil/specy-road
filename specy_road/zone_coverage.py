"""Plan-time zone coverage warnings for orchestrate plan and grind-session --plan."""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath
from typing import Iterable

from specy_road.finish_implementation_check import in_zones
from specy_road.git_subprocess import git_stdout
from specy_road.runtime_paths import project_prefix, rebase_to_project

NEW_OUTSIDE = "new file outside zones"
BEST_EFFORT_HINT = (
    "best-effort path detection; misses are accepted — see uncovered_acceptance_paths"
)
_BACKTICK = re.compile(r"`([^`]+)`")
_SLASH_TOKEN = re.compile(r"(?<![\w./-])([A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+)(?![\w./-])")
_BARE_DIR = re.compile(r"(?<![\w./-])([A-Za-z0-9_.-]+/)(?![\w./-])")
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
    """Tracked file, or directory that contains a tracked path (with or without trailing ``/``)."""
    for form in _path_forms(path, prefix):
        if form in tracked:
            return True
        head = f"{form}/"
        if any(p.startswith(head) for p in tracked):
            return True
    return False


def _tokens(line: str) -> list[tuple[str, bool, bool]]:
    """``(normalized path, backtick, had_trailing_slash)``."""
    seen: set[str] = set()
    out: list[tuple[str, bool, bool]] = []

    def add(raw: str, backtick: bool) -> None:
        parsed = _normalize(raw)
        if parsed and parsed[0] not in seen:
            seen.add(parsed[0])
            out.append((parsed[0], backtick, parsed[1]))

    for raw in _BACKTICK.findall(line):
        add(raw, True)
    scrub = _BACKTICK.sub(" ", line)
    for raw in _SLASH_TOKEN.findall(scrub):
        add(raw, False)
    for raw in _BARE_DIR.findall(scrub):
        add(raw, False)
    return out


def _is_candidate(path: str, *, backtick: bool, had_slash: bool, top_dirs: set[str]) -> bool:
    if backtick:
        return "/" in path or had_slash or _has_known_suffix(path)
    head = path.split("/", 1)[0]
    return head in top_dirs or _has_known_suffix(path)


def _tracked_paths(root: Path, ref: str) -> set[str] | None:
    out = git_stdout(["ls-tree", "-r", "--full-tree", "-z", ref], root)
    if out is None:
        return None
    paths: set[str] = set()
    for rec in filter(None, out.split("\0")):
        _, path = rec.split("\t", 1)
        paths.add(path)
    return paths


def uncovered_acceptance_paths(
    root: Path,
    node: dict,
    *,
    ref: str = "HEAD",
    tracked: set[str] | None = None,
) -> list[str]:
    """Return warning labels for acceptance path candidates outside the leaf's touch zones.

    **Best-effort path rule (A1; false negatives accepted).** From each acceptance line:

    * **Backtick candidate:** the quoted span contains ``/`` or ends in a known suffix
      (``.py``, ``.md``, ``.json``, ``.yaml``, ``.yml``, ``.toml``, ``.ts``, ``.tsx``,
      ``.sh``, ``.txt``, ``.cfg``, ``.ini``). Always treated as a path candidate.
    * **Bare candidate:** a bare token starts with a tracked top-level directory name
      at ``ref`` or ends in one of those suffixes (includes bare ``docs/`` when ``docs``
      is tracked).
    * **Ignored:** other prose (``input/output``, ``read/write``, ``M12/M13``, URLs, …).

    For each candidate not covered by a touch zone: if it is an existing tracked file
    or directory (with or without a trailing ``/`` on the token), list that path; otherwise
    list :data:`NEW_OUTSIDE` once per leaf (nonexistent backtick paths such as
    ``brand/newdir`` count as new even when no parent directory is tracked yet).
    """
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
            if not _is_candidate(path, backtick=backtick, had_slash=had_slash, top_dirs=top_dirs):
                continue
            if in_zones(zones, path, prefix):
                continue
            if _exists(path, tree, prefix):
                if path not in labels:
                    labels.append(path)
            else:
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
