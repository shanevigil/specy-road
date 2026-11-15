"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

from pathlib import Path
from specy_road.agents_md_block import injected_context

def rels(root: Path, harness: str) -> list[str]:
    """Shared test helper."""
    return [f.rel for f in injected_context(root)[harness]]
