"""Interactive task picker for do-next-available-task."""

from __future__ import annotations

import sys
def pick_interactive(available: list[dict], all_nodes: list[dict]) -> dict:
    children_by_parent: dict[str, list[str]] = {}
    for node in all_nodes:
        parent_id = node.get("parent_id")
        if isinstance(parent_id, str) and parent_id:
            children_by_parent.setdefault(parent_id, []).append(node["id"])
    available_by_id = {n["id"]: n for n in available}
    all_by_id = {n["id"]: n for n in all_nodes}
    key_to_id = {
        x["node_key"]: x["id"]
        for x in all_nodes
        if isinstance(x.get("node_key"), str) and x.get("node_key")
    }
    print(f"Available actionable leaves ({len(available)}):\n")
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
    while True:
        try:
            raw = input("Select leaf number or leaf id (q to quit): ").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            raise SystemExit(0)
        if raw.lower() in ("q", "quit", ""):
            raise SystemExit(0)
        if raw in available_by_id:
            return available_by_id[raw]
        if raw in all_by_id and children_by_parent.get(raw):
            print(
                f"Cannot claim parent node {raw!r} directly; "
                "select an actionable descendant leaf.",
                file=sys.stderr,
            )
            continue
        try:
            idx = int(raw) - 1
            if not 0 <= idx < len(available):
                raise ValueError
        except ValueError:
            print(f"Invalid selection: {raw!r}", file=sys.stderr)
            continue
        return available[idx]
