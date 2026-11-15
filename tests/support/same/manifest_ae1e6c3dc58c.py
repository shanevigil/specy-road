"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

from pathlib import Path
import json

def manifest(root: Path) -> dict:
    """Shared test helper."""
    return json.loads((root / ".specyrd" / "manifest.json").read_text(encoding="utf-8"))
