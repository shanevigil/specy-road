"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

from pathlib import Path

def _prefer(repo: Path, *extra: str) -> list[str]:
    return ["decisions", "add", "--repo-root", str(repo), "--kind", "preference", *extra]
