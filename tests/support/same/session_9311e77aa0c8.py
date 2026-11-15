"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

from pathlib import Path
from specy_road.brainstorm_session import read_session

SLUG = "how-do-we-expand-payments"

def session(repo: Path):
    """Shared test helper."""
    return read_session(repo, SLUG)
