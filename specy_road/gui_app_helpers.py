"""Path and ID helpers for the PM Gantt HTTP API (requires bundled_scripts on sys.path)."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import HTTPException

from roadmap_gui_lib import resolve_repo_root


def get_repo_root(pkg_parent: Path) -> Path:
    env = os.environ.get("SPECY_ROAD_REPO_ROOT")
    if env:
        return Path(env).resolve()
    return resolve_repo_root(pkg_parent)


def safe_rel_path(repo_root: Path, rel: str) -> Path:
    """Resolve a repo-relative path, rejecting empty paths and ``..`` segments."""
    raw = (rel or "").strip().replace("\\", "/").lstrip("/")
    if not raw or ".." in raw.split("/"):
        raise HTTPException(status_code=400, detail="invalid path")
    p = (repo_root / raw).resolve()
    try:
        p.relative_to(repo_root.resolve())
    except ValueError as e:
        raise HTTPException(status_code=400, detail="path escapes repo") from e
    return p


def assert_under_allowed_root(repo_root: Path, path: Path, allowed_top: str) -> None:
    """Require ``path`` to resolve under ``repo_root/<allowed_top>/``."""
    allowed = (repo_root / allowed_top).resolve()
    try:
        path.resolve().relative_to(allowed)
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"path must stay under {allowed_top}/",
        ) from e


def next_child_id(nodes: list[dict], parent_id: str | None) -> str:
    """Next display id among siblings: ``M{n}`` at the root, ``<parent>.<n>`` when nested."""
    children = [n["id"] for n in nodes if n.get("parent_id") == parent_id]
    if parent_id is None:
        nums: list[int] = []
        for cid in children:
            if cid.startswith("M") and "." not in cid[1:]:
                try:
                    nums.append(int(cid[1:]))
                except ValueError:
                    continue
        n = max(nums, default=-1) + 1
        return f"M{n}"
    prefix = parent_id + "."
    nums = []
    for cid in children:
        if cid.startswith(prefix):
            tail = cid[len(prefix) :]
            if tail.isdigit():
                nums.append(int(tail))
    n = max(nums, default=0) + 1
    return f"{parent_id}.{n}"
