"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

from pathlib import Path
from specy_road.roadmap_load import load_roadmap

def _by_id(root: Path) -> dict[str, dict]:
    return {n["id"]: n for n in load_roadmap(root)["nodes"]}
