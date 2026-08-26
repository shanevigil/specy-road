"""Seed ``roadmap/activity.json`` from git history.

Live write points only start recording from the moment they ship, so an
established repo would show an empty last-worked-on column for years of real
work. Backfill derives a timestamp per node from the last commit that touched
its planning sheet.

The result is explicitly a **lower bound** — it is recorded with kind
``backfilled`` so nothing mistakes a derived timestamp for an observed one.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from specy_road.activity_log import (
    KIND_BACKFILLED,
    load_activity,
    set_activity,
    write_activity,
)


def last_commit_iso(root: Path, rel_path: str) -> str | None:
    """Author date of the last commit touching ``rel_path``, ISO 8601."""
    try:
        r = subprocess.run(
            ["git", "log", "-1", "--format=%aI", "--", rel_path],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
    except (OSError, ValueError):
        return None
    if r.returncode != 0:
        return None
    out = (r.stdout or "").strip()
    return out or None


def backfill_plan(root: Path) -> list[tuple[str, str, str]]:
    """``(node_id, node_key, timestamp)`` for every node git can date.

    Nodes with no planning sheet, or whose sheet has never been committed, are
    skipped rather than guessed at.
    """
    from roadmap_load import load_roadmap

    out: list[tuple[str, str, str]] = []
    for n in load_roadmap(root)["nodes"]:
        key = n.get("node_key")
        sheet = n.get("planning_dir")
        if not isinstance(key, str) or not isinstance(sheet, str) or not sheet.strip():
            continue
        when = last_commit_iso(root, sheet.strip())
        if when:
            out.append((str(n.get("id")), key, when))
    return out


def backfill_activity(root: Path, *, dry_run: bool = False) -> dict[str, Any]:
    """Record a ``backfilled`` timestamp for every datable node.

    ``set_activity`` keeps the later timestamp, so this never overwrites real
    observed activity with an older derived one — the two can run in any order.
    """
    plan = backfill_plan(root)
    if dry_run:
        return {"applied": 0, "candidates": len(plan), "entries": plan}

    doc = load_activity(root)
    before = dict(doc.get("nodes") or {})
    for _, key, when in plan:
        set_activity(doc, key, KIND_BACKFILLED, when)
    write_activity(root, doc)
    changed = sum(1 for k, v in doc["nodes"].items() if before.get(k) != v)
    return {"applied": changed, "candidates": len(plan), "entries": plan}
