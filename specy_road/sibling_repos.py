"""Sibling repositories: git repositories under the project root that the root repository cannot see.

A sibling is the top of its own git repository (its own ``.git``, file or directory), at most two
directories below the project root, that the root repository ignores or does not track, and that
``nested_repos`` does not configure. Changes there never show in the root repository's diffs, so the
review gate never carries an approval across commits while one exists, and records the sibling HEADs
an approval saw (``sibling_heads``).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from specy_road.git_subprocess import git_code, git_text
from specy_road.nested_repos import in_nested, is_repo_top, nested_prefixes
from specy_road.runtime_paths import project_prefix

#: Directories never searched: git's own, specy-road's runtime state (worktrees live there), dependencies.
_SKIP = frozenset({".git", "work", "node_modules"})
_DEPTH = 2


@dataclass(frozen=True)
class Sibling:
    path: str          # project-relative, posix
    head: str | None   # ``None`` when the repository has no commit yet
    dirty: bool


def _untracked_by_root(project_root: Path, rel: str) -> bool:
    if not git_text(["ls-files", "--", rel], project_root):
        return True
    return git_code(["check-ignore", "-q", "--", rel], project_root)[0] == 0


def sibling_repos(project_root: Path) -> list[Sibling]:
    """Each sibling repository under ``project_root``, sorted by path; none outside a git checkout."""
    if git_text(["rev-parse", "--show-toplevel"], project_root) is None:
        return []
    prefix, configured = project_prefix(project_root), nested_prefixes(project_root)
    found: list[Sibling] = []

    def walk(d: Path, depth: int) -> None:
        try:
            children = sorted(c for c in d.iterdir() if c.is_dir() and not c.is_symlink() and c.name not in _SKIP)
        except OSError:
            return
        for c in children:
            rel = c.relative_to(project_root).as_posix()
            if in_nested(f"{prefix}{rel}", configured):
                continue
            if (c / ".git").exists() and is_repo_top(c):
                if _untracked_by_root(project_root, rel):
                    status = git_text(["status", "--porcelain"], c)
                    found.append(Sibling(rel, git_text(["rev-parse", "HEAD"], c), bool(status) or status is None))
                continue   # another repository's inside is not the root's to search
            if depth < _DEPTH:
                walk(c, depth + 1)

    walk(project_root, 1)
    return found


def sibling_heads(project_root: Path) -> dict[str, str]:
    """``{path: HEAD}`` of each sibling repository that has a commit, for READY and review records."""
    return {s.path: s.head for s in sibling_repos(project_root) if s.head}


def sibling_heads_field(project_root: Path) -> dict[str, dict[str, str]]:
    """``{"sibling_heads": ...}`` to merge into a READY or review record, or ``{}`` when there are none."""
    return {"sibling_heads": heads} if (heads := sibling_heads(project_root)) else {}


def warn_unconfigured_sibling_repos(root: Path) -> list[str]:
    """One non-fatal stderr line naming the sibling repositories, when there are any; returns their paths."""
    paths = [s.path for s in sibling_repos(root)]
    if paths:
        print(f"roadmap: warning — git repositories under the project root are not configured in nested_repos "
              f"({', '.join(paths)}): the review gate cannot see changes in them, so an approval never carries "
              "to a later commit; configure them as described in docs/git-workflow.md, "
              "\"Nested repositories (`nested_repos`)\"", file=sys.stderr)
    return paths
