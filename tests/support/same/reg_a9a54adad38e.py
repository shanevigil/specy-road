"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

def _reg(*node_ids: str) -> dict:
    return {
        "version": 1,
        "entries": [{"node_id": nid, "codename": nid} for nid in node_ids],
    }
