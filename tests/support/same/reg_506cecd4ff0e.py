"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

def _reg(*entries):
    return {"version": 1, "entries": list(entries)}
