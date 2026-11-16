"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from specy_road.roadmap_crud_ops import cmd_edit

def edit(repo: Path, *sets: str) -> None:
    """Shared test helper."""
    cmd_edit(SimpleNamespace(repo_root=str(repo), node_id="M1.1", set=list(sets), sync_codename=False))
