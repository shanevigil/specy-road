"""Plan-time check: acceptance criteria that name repo paths the leaf's zones do not cover.

Extracts path-like tokens from each acceptance line (backticks, or slash-containing
words that exist at ``ref`` or end in a known extension), then compares them to the
node's ``touch_zones`` via :func:`specy_road.finish_implementation_check.in_zones`.
Used by ``orchestrate plan`` and ``grind-session --plan``.
"""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath
from typing import Iterable

from specy_road.finish_implementation_check import in_zones
from specy_road.git_subprocess import git_stdout
from specy_road.runtime_paths import project_prefix, rebase_to_project

NEW_OUTSIDE = "new file outside zones"
_BACKTICK = re.compile(r"`([^`]+)`")
_SLASH_TOKEN = re.compile(r"(?<![\w./-])([A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+)(?![\w./-])")
_KNOWN_SUFFIXES = (
    ".py", ".md", ".json", ".yaml", ".yml", ".toml", ".js", ".ts", ".tsx", ".jsx",
    ".css", ".html", ".sh", ".txt", ".rst", ".ini", ".cfg", ".sql", ".xml",
)


def _acceptance(node: dict) -> list[str]:
    raw = node.get("acceptance") or []
    return [a.strip() for a in raw if isinstance(a, str) and a.strip()]


def _zones(node: dict) -> list[str]:
    return [z.strip().strip("/") for z in (node.get("touch_zones") or []) if isinstance(z, str) and z.strip()]


def _normalize(token: str) -> str | None:
    t = token.strip().strip(".,;:)\"'")
    if not t or t.startswith(("http://", "https://", "-", "/")) or ".." in t.split("/"):
        return None
    return t.removeprefix("./").rstrip("/") or None


def _path_like(token: str, tracked: set[str], prefix: str) -> bool:
    if "/" in token:
        return True
    if PurePosixPath(token).suffix.lower() in _KNOWN_SUFFIXES:
        return True
    forms = {token, f"{prefix}{token}" if prefix else token}
    if prefix:
        forms.add(rebase_to_project(token, prefix) or token)
    return any(f in tracked for f in forms)


def _tokens(line: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in _BACKTICK.findall(line):
        norm = _normalize(raw)
        if norm and norm not in seen:
            seen.add(norm)
            out.append(norm)
    scrub = _BACKTICK.sub(" ", line)
    for raw in _SLASH_TOKEN.findall(scrub):
        norm = _normalize(raw)
        if norm and norm not in seen:
            seen.add(norm)
            out.append(norm)
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


def _exists(path: str, tracked: set[str], prefix: str) -> bool:
    forms = {path}
    if prefix:
        forms.add(f"{prefix}{path}")
        rebased = rebase_to_project(path, prefix)
        if rebased:
            forms.add(rebased)
    return any(f in tracked for f in forms)


def uncovered_acceptance_paths(
    root: Path,
    node: dict,
    *,
    ref: str = "HEAD",
    tracked: set[str] | None = None,
) -> list[str]:
    """Labels for paths acceptance names that no touch zone covers.

    Existing repo paths are listed by path; non-existent paths with no zone
    prefix are grouped as :data:`NEW_OUTSIDE`.
    """
    zones = _zones(node)
    lines = _acceptance(node)
    if not lines:
        return []
    prefix = project_prefix(root)
    tree = tracked if tracked is not None else _tracked_paths(root, ref)
    if tree is None:
        return []
    labels: list[str] = []
    new_outside = False
    for line in lines:
        for path in _tokens(line):
            if not _path_like(path, tree, prefix):
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
        f"{node_id}: acceptance names paths outside touch zones: "
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
