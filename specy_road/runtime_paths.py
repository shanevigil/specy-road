"""Paths for bundled kit scripts, and the one project-root resolver.

**Two roots, deliberately named apart.** Nearly every path bug in this toolkit
comes from conflating them:

* the **git root** owns ``.gitignore``, ``.cursorindexingignore``, ``.claude/``,
  ``.cursor/`` and ``.specyrd/`` — files that belong to the checkout;
* the **project root** owns ``roadmap/``, ``planning/``, ``shared/``, ``work/``,
  ``constitution/`` and ``constraints/`` — the specy-road tree itself.

They coincide in the *embedded* layout, where the roadmap sits at the repo
root. They do not in the *nested* layout, where the whole tree lives under a
subfolder (``sr/``) to keep the coding root uncluttered. Anything written to
the first that names paths inside the second must be prefixed by
:func:`project_prefix`.

**Why one resolver.** The CLI and the PM GUI used to resolve the project by
different rules, and the CLI's was the weaker one: it was git-toplevel-or-cwd
and never read ``SPECY_ROAD_REPO_ROOT`` at all, despite ``docs/pm-workflow.md``
telling people to set it. It had no discovery either, so in a nested layout
every single invocation needed an explicit ``--repo-root``. Both surfaces now
call :func:`project_root`.

**Recorded, not guessed.** Discovery alone is not enough — a repository can
contain two roadmaps, and a scan will eventually pick the wrong one silently.
``.specyrd/manifest.json`` is already tracked and versioned, so the layout is
recorded there and discovery is only the fallback.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

#: Overrides discovery for both the CLI and the GUI.
REPO_ROOT_ENV = "SPECY_ROAD_REPO_ROOT"

#: Where the layout is recorded, relative to the **git** root.
SPECYRD_MANIFEST = Path(".specyrd") / "manifest.json"

#: Marker that identifies a project root during discovery.
ROADMAP_MANIFEST = Path("roadmap") / "manifest.json"


def specy_road_package_dir() -> Path:
    """Directory containing the ``specy_road`` package (``__init__.py``)."""
    return Path(__file__).resolve().parent


def bundled_scripts_dir() -> Path:
    """Directory with roadmap validators and helpers (shipped in the wheel)."""
    return specy_road_package_dir() / "bundled_scripts"


def _git(args: list[str], cwd: Path) -> str | None:
    try:
        r = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, NotADirectoryError):
        return None
    return r.stdout.strip()


def git_root(start: Path | None = None) -> Path | None:
    """The enclosing git worktree root, or ``None`` outside one."""
    out = _git(["rev-parse", "--show-toplevel"], start or Path.cwd())
    return Path(out).resolve() if out else None


def project_prefix(root: Path) -> str:
    """``root``'s path within its git repo, e.g. ``"sr/"`` — or ``""``.

    The bridge between the two roots. A path that ``git log`` reports, or that
    ``.gitignore`` matches, is relative to the **git** root; roadmap paths are
    relative to the **project** root. Prefix to go one way, strip to go back.
    """
    return _git(["rev-parse", "--show-prefix"], root) or ""


def prefix_within(git_top: Path, project: Path) -> str:
    """:func:`project_prefix` computed from two paths instead of from git.

    Needed at ``init`` time, when the project directory may not be committed
    yet and ``git rev-parse --show-prefix`` would have nothing to report.
    """
    try:
        rel = project.resolve().relative_to(git_top.resolve())
    except ValueError:
        return ""
    return "" if str(rel) == "." else rel.as_posix() + "/"


def recorded_project_root(git_top: Path) -> Path | None:
    """The project root this checkout recorded, if it recorded one.

    Read straight from JSON rather than through ``specyrd_init`` so that the
    resolver stays importable from anywhere without a dependency cycle.
    """
    path = git_top / SPECYRD_MANIFEST
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    rel = data.get("project_root") if isinstance(data, dict) else None
    if not isinstance(rel, str) or not rel.strip() or rel.strip() == ".":
        return None
    if Path(rel).is_absolute() or ".." in Path(rel).parts:
        return None  # a recorded root may not escape its own checkout
    candidate = (git_top / rel).resolve()
    return candidate if candidate.is_dir() else None


def discover_project_root(start: Path | None = None) -> Path | None:
    """Nearest ancestor of ``start`` holding ``roadmap/manifest.json``."""
    here = (start or Path.cwd()).resolve()
    for anc in [here, *here.parents]:
        if (anc / ROADMAP_MANIFEST).is_file():
            return anc
    return None


def project_root(explicit: Path | str | None = None) -> Path:
    """Resolve the specy-road project root.

    Order, most explicit first: the ``--repo-root`` a caller passed, then
    ``SPECY_ROAD_REPO_ROOT``, then the root recorded in
    ``.specyrd/manifest.json``, then discovery upward from the working
    directory, then the git root, then the working directory.
    """
    if explicit:
        return Path(explicit).resolve()
    env = os.environ.get(REPO_ROOT_ENV)
    if env and env.strip():
        return Path(env.strip()).resolve()
    top = git_root()
    if top is not None:
        recorded = recorded_project_root(top)
        if recorded is not None:
            return recorded
    discovered = discover_project_root()
    if discovered is not None:
        return discovered
    return top if top is not None else Path.cwd().resolve()


def source_scan_root(project: Path) -> Path:
    """Where a project's *source-code* globs are anchored.

    ``constraints/file-limits.yaml`` belongs to the project root, but the globs
    inside it name the consumer's own code — ``frontend/**/*.tsx`` — which stays
    at the git root even when the specy-road tree moves under ``sr/``. Anchoring
    those globs at the project root would match nothing and quietly enforce no
    limits at all.

    Widened only when ``project`` really is this checkout's recorded project
    root. Pointing ``--repo-root`` at an arbitrary subdirectory — a fixture
    tree, say — must scan that subtree and not escape upward into the checkout
    that happens to contain it.
    """
    top = git_root(project)
    if top is None or top == project.resolve():
        return project.resolve()
    recorded = recorded_project_root(top)
    if recorded is not None and recorded == project.resolve():
        return top
    return project.resolve()


def default_user_repo_root() -> Path:
    """Backwards-compatible alias for :func:`project_root`.

    Kept because roughly sixty call sites spell the fallback as
    ``Path(ns.repo_root or default_user_repo_root()).resolve()``; routing them
    through one resolver was the point, churning them was not.
    """
    return project_root()
