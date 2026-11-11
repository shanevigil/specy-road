"""When ``specy-road validate`` should remind the repo to run ``chore garden``.

The reminder reads the garden record and the cadence policy. It does not import
the garden scanner or roadmap CRUD, so validate does not close that cycle.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

from specy_road.orchestration_config import effective_config


def record_path(root: Path) -> Path:
    """A dot-file: a chore slug starts with a letter or digit, so no chore record can be this file."""
    from specy_road.chore_records import chores_dir   # the worker records stack, only when read

    return chores_dir(root) / ".garden.json"


def garden_due(root: Path, today: date) -> str | None:
    """Why gardening is due under ``policy.garden_cadence_days``; ``None`` when it is not or the key is unset.

    The arithmetic of a research register entry: due when more than the cadence's days have passed.
    """
    cadence = effective_config(root)[0]["policy"].get("garden_cadence_days")
    if not cadence:
        return None
    try:
        last = date.fromisoformat(json.loads(record_path(root).read_text(encoding="utf-8"))["last_run"])
    except (OSError, ValueError, KeyError, TypeError):
        last = None
    if last is not None and (today - last).days <= cadence:
        return None
    when = "never run" if last is None else f"last run {last}"
    return f"gardening due: {when}, every {cadence} days; run `specy-road chore garden`"


def warn_garden_due(root: Path, today: date | None = None) -> None:
    """One non-fatal ``validate`` line when gardening is due."""
    why = garden_due(root, today or date.today())
    if why:
        print(f"garden: warning — {why} (see docs/orchestration-chores.md)", file=sys.stderr)
