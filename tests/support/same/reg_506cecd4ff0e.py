"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

def reg(*entries):
    """Shared test helper."""
    return {"version": 1, "entries": list(entries)}
