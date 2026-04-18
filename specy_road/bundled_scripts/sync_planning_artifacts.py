"""Batch-sync ``planning_dir`` and on-disk feature sheets after display id / codename changes."""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from planning_artifacts import normalize_planning_dir, resolve_planning_path
from roadmap_edit_fields import sync_planning_dir_filename


def sync_planning_artifacts(repo_root: Path, nodes: list[dict]) -> None:
    """
    For every node that has ``planning_dir`` set, set it to the canonical path from
    ``planning/<id>_<slug>_<node_key>.md`` and rename files on disk when the path changes.

    Uses a temporary directory at the repo root (not under ``planning/``) so swaps and
    chains of renames do not clobber files and validators do not see stray ``*.md``.
    Safe to call when display ``id`` values changed (e.g. after
    ``renumber_display_ids_inplace``). Mutates ``nodes`` in place.

    If the old path had no file (already wrong), only updates JSON; if the new path
    already exists and is not the source of another move, leaves disk unchanged for
    that edge (validator may report issues).
    """
    root = repo_root.resolve()
    moves: list[tuple[str, str, str]] = []  # node_key, old_rel, new_rel

    for n in nodes:
        pd = n.get("planning_dir")
        if not isinstance(pd, str) or not pd.strip():
            continue
        try:
            old_norm = normalize_planning_dir(pd.strip())
        except ValueError:
            continue
        canon = sync_planning_dir_filename(n)
        if canon is None:
            continue
        nk = n.get("node_key")
        if not isinstance(nk, str) or not nk:
            continue
        n["planning_dir"] = canon
        if old_norm != canon:
            moves.append((nk, old_norm, canon))

    if not moves:
        return

    staging_name = f".specy-road-planning-sync-{uuid.uuid4().hex[:12]}"
    staging = root / staging_name
    staging.mkdir(parents=True, exist_ok=True)
    try:
        for nk, old_rel, _new_rel in moves:
            old_p = resolve_planning_path(root, old_rel)
            if not old_p.is_file():
                continue
            dest = staging / f"{nk}.md"
            if dest.exists():
                raise ValueError(f"sync_planning_artifacts: staging collision for {nk!r}")
            old_p.rename(dest)

        for nk, _old_rel, new_rel in moves:
            src = staging / f"{nk}.md"
            new_p = resolve_planning_path(root, new_rel)
            new_p.parent.mkdir(parents=True, exist_ok=True)
            if src.is_file():
                if new_p.exists() and new_p.resolve() != src.resolve():
                    raise ValueError(
                        f"sync_planning_artifacts: target exists {new_p.relative_to(root)}",
                    )
                src.rename(new_p)
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
