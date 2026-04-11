"""Paths for bundled kit scripts and default user project root (git / cwd)."""

from __future__ import annotations

import subprocess
from pathlib import Path


def specy_road_package_dir() -> Path:
    """Directory containing the ``specy_road`` package (``__init__.py``)."""
    return Path(__file__).resolve().parent


def bundled_scripts_dir() -> Path:
    """Directory with roadmap validators and helpers (shipped in the wheel)."""
    return specy_road_package_dir() / "bundled_scripts"


def default_user_repo_root() -> Path:
    """Prefer git worktree root; else current working directory."""
    cwd = Path.cwd()
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
        )
        return Path(r.stdout.strip()).resolve()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return cwd.resolve()


def specy_road_source_repo_root() -> Path | None:
    """Return source repo root (parent of ``specy_road/``) when in a checkout."""
    pkg = specy_road_package_dir()
    candidate = pkg.parent
    has_pkg = (candidate / "specy_road").is_dir()
    has_py = (candidate / "pyproject.toml").is_file()
    if has_pkg and has_py:
        return candidate.resolve()
    return None
