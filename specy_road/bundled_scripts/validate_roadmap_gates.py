"""Validation rules for roadmap ``type: gate`` nodes."""

from __future__ import annotations

import sys
from typing import Any


def validate_gates(nodes: list[dict[str, Any]]) -> None:
    """Gate nodes are leaf-only under vision or phase."""
    by_id = {n["id"]: n for n in nodes}
    for n in nodes:
        if n.get("type") != "gate":
            continue
        nid = n["id"]
        for c in nodes:
            if c.get("parent_id") == nid:
                print(
                    f"roadmap: gate {nid} cannot have child nodes",
                    file=sys.stderr,
                )
                raise SystemExit(1)
        pid = n.get("parent_id")
        if pid in (None, ""):
            print(
                f"roadmap: gate {nid} must have parent_id set to "
                "a vision or phase node",
                file=sys.stderr,
            )
            raise SystemExit(1)
        parent = by_id.get(str(pid))
        if not parent:
            continue
        pt = parent.get("type")
        if pt not in ("vision", "phase"):
            print(
                "roadmap: gate "
                f"{nid!r} must be a direct child of vision or phase "
                f"(parent {pid!r} has type {pt!r})",
                file=sys.stderr,
            )
            raise SystemExit(1)
