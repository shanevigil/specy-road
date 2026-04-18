"""Rename flat planning ``.md`` when ``planning_dir`` path changes (e.g. codename edit)."""

from __future__ import annotations

from pathlib import Path

from planning_artifacts import normalize_planning_dir, resolve_planning_path


def rename_planning_file_if_path_changed(
    repo_root: Path,
    old_rel: str | None,
    new_rel: str | None,
) -> None:
    """If both paths are under ``planning/`` and differ, ``git mv``-style rename on disk."""
    if not old_rel or not new_rel:
        return
    try:
        o = normalize_planning_dir(old_rel.strip())
        n = normalize_planning_dir(new_rel.strip())
    except ValueError:
        return
    if o == n:
        return
    old_p = resolve_planning_path(repo_root, o)
    new_p = resolve_planning_path(repo_root, n)
    if not old_p.is_file():
        return
    new_p.parent.mkdir(parents=True, exist_ok=True)
    if new_p.exists() and new_p != old_p:
        return
    old_p.rename(new_p)
