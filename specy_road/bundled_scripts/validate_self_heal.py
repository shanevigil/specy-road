"""Self-healing helpers run by ``specy-road validate`` before strict checks.

F-006/F-008: validate should fix deterministic issues silently (codenames,
deprecated-field scrubbing) and surface only problems that require human
intervention.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterable

from roadmap_chunk_utils import (
    build_node_chunk_map,
    load_json_chunk,
    write_json_chunk,
)
from roadmap_edit_fields import (
    title_to_codename,
    update_planning_dir_to_canonical,
)
from planning_rename import rename_planning_file_if_path_changed

# Fields that were part of the schema before F-003/F-007 and should now be
# silently stripped from any chunk file that still carries them.
_DEPRECATED_FIELDS: tuple[str, ...] = ("execution_subtask", "agentic_checklist")


def _codename_collision_suffix(node_key: str) -> str:
    """Return a short suffix from the UUID tail for collision disambiguation."""
    # UUIDs use `-` separators; grab the last 4 hex characters of the last group.
    tail = (node_key or "").replace("-", "")
    return (tail[-4:] or "x").lower()


def _derive_codename(title: str, node_key: str, existing: set[str]) -> str | None:
    """
    Derive a valid kebab-case codename from ``title``. If it collides with
    ``existing``, append ``-<4 hex>``; if still colliding, extend to 6 hex.
    Returns None if the title yields no valid slug.
    """
    slug = title_to_codename(title)
    if not slug:
        return None
    if slug not in existing:
        return slug
    suffix = _codename_collision_suffix(node_key)
    cand = f"{slug}-{suffix}"
    if cand not in existing:
        return cand
    tail_long = (node_key or "").replace("-", "")
    long_suffix = (tail_long[-6:] or "xx").lower()
    cand = f"{slug}-{long_suffix}"
    return cand


def _logs_append(logs: list[str], msg: str) -> None:
    logs.append(msg)
    # Print to stderr immediately so operators see progress even on large trees.
    print(msg, file=sys.stderr)


def _heal_one_chunk(
    chunk_path: Path,
    existing_codenames: set[str],
    logs: list[str],
    root: Path,
) -> bool:
    """Heal one chunk file in place. Returns True if the file changed."""
    nodes = load_json_chunk(chunk_path)
    changed = False
    for node in nodes:
        if not isinstance(node, dict):
            continue
        # 1. Strip deprecated fields (F-003/F-007).
        for key in _DEPRECATED_FIELDS:
            if key in node:
                _logs_append(
                    logs,
                    f"[heal] node {node.get('id', '?')}: stripped deprecated "
                    f"field {key!r} (see F-003/F-007).",
                )
                node.pop(key, None)
                changed = True
        # 2. Auto-derive missing codenames (F-006).
        if node.get("type") == "task":
            cn = node.get("codename")
            if not cn:
                derived = _derive_codename(
                    str(node.get("title") or ""),
                    str(node.get("node_key") or ""),
                    existing_codenames,
                )
                if derived:
                    node["codename"] = derived
                    existing_codenames.add(derived)
                    # Rename planning file to match codename (the canonical
                    # slug used in planning/<id>_<slug>_<node_key>.md).
                    old_pd = node.get("planning_dir")
                    if isinstance(old_pd, str) and old_pd.strip():
                        old_pd_norm = old_pd.strip()
                        update_planning_dir_to_canonical(node)
                        new_pd = node.get("planning_dir")
                        if isinstance(new_pd, str) and new_pd != old_pd_norm:
                            rename_planning_file_if_path_changed(
                                root, old_pd_norm, new_pd
                            )
                    _logs_append(
                        logs,
                        f"[heal] node {node.get('id', '?')}: codename "
                        f"auto-derived as {derived!r}.",
                    )
                    changed = True
    if changed:
        write_json_chunk(chunk_path, nodes)
    return changed


def _existing_codenames(chunk_paths: Iterable[Path]) -> set[str]:
    out: set[str] = set()
    for p in chunk_paths:
        for n in load_json_chunk(p):
            if isinstance(n, dict):
                cn = n.get("codename")
                if isinstance(cn, str) and cn:
                    out.add(cn)
    return out


def auto_heal_roadmap(root: Path) -> tuple[bool, list[str]]:
    """
    Walk every roadmap chunk and apply deterministic fixes. Returns
    ``(any_changed, log_lines)``.

    Safe to run multiple times; if nothing needs fixing, returns False and [].
    """
    logs: list[str] = []
    chunk_map = build_node_chunk_map(root)
    chunk_paths: set[Path] = set(chunk_map.values())
    if not chunk_paths:
        return False, logs

    existing = _existing_codenames(chunk_paths)
    any_changed = False
    # Deterministic order: sort paths before processing.
    for chunk_path in sorted(chunk_paths):
        if _heal_one_chunk(chunk_path, existing, logs, root):
            any_changed = True
    return any_changed, logs
