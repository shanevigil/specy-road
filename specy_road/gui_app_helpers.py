"""Path and ID helpers for the PM Gantt HTTP API."""

from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException

from specy_road.bundled_scripts.roadmap_layout import next_child_id
from specy_road.runtime_paths import project_root

#: Retained for callers that imported it before the resolver was unified.


def get_repo_root() -> Path:
    """The project root, resolved exactly as every CLI command resolves it.

    This used to be the GUI's own rule — env var, then discovery, then git —
    while the CLI did git-toplevel-or-cwd and read no environment at all. The
    two surfaces disagreeing about where the project lives is what made a
    nested layout unusable, so there is now one resolver and the GUI is a
    caller of it.
    """
    return project_root()


def safe_rel_path(repo_root: Path, rel: str) -> Path:
    """Resolve a repo-relative path; reject empty paths and ``..`` segments."""
    raw = (rel or "").strip().replace("\\", "/").lstrip("/")
    if not raw or ".." in raw.split("/"):
        raise HTTPException(status_code=400, detail="invalid path")
    p = (repo_root / raw).resolve()
    try:
        p.relative_to(repo_root.resolve())
    except ValueError as e:
        raise HTTPException(status_code=400, detail="path escapes repo") from e
    return p


def assert_under_allowed_root(
    repo_root: Path,
    path: Path,
    allowed_top: str,
) -> None:
    """Require ``path`` to resolve under ``repo_root/<allowed_top>/``."""
    allowed = (repo_root / allowed_top).resolve()
    try:
        path.resolve().relative_to(allowed)
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"path must stay under {allowed_top}/",
        ) from e


def assert_planning_file_api_path(repo_root: Path, path: Path) -> None:
    """Allow ``planning/``, ``constitution/``, and repo-root ``vision.md``."""
    resolved = path.resolve()
    root = repo_root.resolve()
    try:
        rel = resolved.relative_to(root)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="path escapes repo") from e
    parts = rel.parts
    if parts == ("vision.md",):
        return
    if parts and parts[0] == "planning":
        return
    if parts and parts[0] == "constitution":
        return
    raise HTTPException(
        status_code=400,
        detail=(
            "path must be under planning/ or constitution/, "
            "or vision.md at repo root"
        ),
    )


#: Re-exported: this used to live here, so GUI callers still import it from
#: this module. It moved to keep it reachable from the CLI, which has no
#: fastapi to satisfy this module's import.
__all__ = ["get_repo_root", "next_child_id"]
