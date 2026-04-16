"""Interactive task picker for do-next-available-task."""

from __future__ import annotations

import sys
def pick_interactive(available: list[dict], all_nodes: list[dict]) -> dict:
    key_to_id = {
        x["node_key"]: x["id"]
        for x in all_nodes
        if isinstance(x.get("node_key"), str) and x.get("node_key")
    }
    print(f"Available tasks ({len(available)}):\n")
    for i, n in enumerate(available, 1):
        gate = (
            n.get("execution_milestone")
            or n.get("execution_subtask")
            or "—"
        )
        deps_raw = n.get("dependencies") or []
        dep_labels = [key_to_id.get(k, k) for k in deps_raw]
        deps = ", ".join(dep_labels) or "none"
        print(f"  {i:2}. [{n['id']}] {n.get('title', '')}")
        print(f"       gate: {gate}  deps: {deps}  codename: {n['codename']}")
    print()
    try:
        raw = input("Select task number (q to quit): ").strip()
    except (KeyboardInterrupt, EOFError):
        print()
        raise SystemExit(0)
    if raw.lower() in ("q", "quit", ""):
        raise SystemExit(0)
    try:
        idx = int(raw) - 1
        if not 0 <= idx < len(available):
            raise ValueError
    except ValueError:
        print(f"Invalid selection: {raw!r}", file=sys.stderr)
        raise SystemExit(1)
    return available[idx]
