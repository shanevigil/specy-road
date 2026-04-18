"""Interactive task picker for do-next-available-task."""

from __future__ import annotations

import sys


def _warn_blocked_leaf() -> None:
    print(
        "warning: selected a dependency-blocked leaf on integration; "
        "ensure dependencies are satisfied before work.",
        file=sys.stderr,
    )


def _print_interactive_rows(
    rows: list[tuple[str, dict]],
    *,
    available: list[dict],
    blocked_entries: list[tuple[dict, list[str]]],
    blocked_by_id: dict[str, tuple[dict, list[str]]],
    key_to_id: dict[str, str],
) -> None:
    print(f"Available actionable leaves ({len(available)}):")
    if blocked_entries:
        print(
            f"Dependency-blocked on integration (informational): {len(blocked_entries)}\n",
        )
    else:
        print()

    for i, (kind, n) in enumerate(rows, 1):
        gate = n.get("execution_milestone") or "—"
        deps_raw = n.get("dependencies") or []
        dep_labels = [key_to_id.get(k, k) for k in deps_raw]
        deps = ", ".join(dep_labels) or "none"
        print(f"  {i:2}. [{n['id']}] {n.get('title', '')}")
        print(f"       gate: {gate}  deps: {deps}  codename: {n['codename']}")
        if kind == "blocked":
            unmet = blocked_by_id[n["id"]][1]
            unmet_lbl = [key_to_id.get(k, k) for k in unmet]
            print(
                f"       BLOCKED (integration): unmet dependencies "
                f"{', '.join(unmet_lbl)}"
            )
    print()


def _resolve_interactive_pick(
    raw: str,
    *,
    rows: list[tuple[str, dict]],
    combined_by_id: dict[str, dict],
    blocked_by_id: dict[str, tuple[dict, list[str]]],
    children_by_parent: dict[str, list[str]],
    all_by_id: dict[str, dict],
) -> dict | None:
    """Return picked node, or None to continue prompting."""
    if raw in combined_by_id:
        picked = combined_by_id[raw]
        if raw in blocked_by_id:
            _warn_blocked_leaf()
        return picked
    if raw in all_by_id and children_by_parent.get(raw):
        print(
            f"Cannot claim parent node {raw!r} directly; "
            "select an actionable descendant leaf.",
            file=sys.stderr,
        )
        return None
    try:
        idx = int(raw) - 1
        if not 0 <= idx < len(rows):
            raise ValueError
    except ValueError:
        print(f"Invalid selection: {raw!r}", file=sys.stderr)
        return None
    kind, picked = rows[idx]
    if kind == "blocked":
        _warn_blocked_leaf()
    return picked


def pick_interactive(
    available: list[dict],
    all_nodes: list[dict],
    *,
    blocked_entries: list[tuple[dict, list[str]]] | None = None,
) -> dict:
    children_by_parent: dict[str, list[str]] = {}
    for node in all_nodes:
        parent_id = node.get("parent_id")
        if isinstance(parent_id, str) and parent_id:
            children_by_parent.setdefault(parent_id, []).append(node["id"])
    available_by_id = {n["id"]: n for n in available}
    blocked_entries = blocked_entries or []
    blocked_by_id = {n["id"]: (n, unmet) for n, unmet in blocked_entries}
    all_by_id = {n["id"]: n for n in all_nodes}
    key_to_id = {
        x["node_key"]: x["id"]
        for x in all_nodes
        if isinstance(x.get("node_key"), str) and x.get("node_key")
    }

    rows: list[tuple[str, dict]] = [("ready", n) for n in available] + [
        ("blocked", n) for n, _u in blocked_entries
    ]

    _print_interactive_rows(
        rows,
        available=available,
        blocked_entries=blocked_entries,
        blocked_by_id=blocked_by_id,
        key_to_id=key_to_id,
    )
    combined_by_id = {**available_by_id, **{x[0]["id"]: x[0] for x in blocked_entries}}

    while True:
        try:
            raw = input("Select leaf number or leaf id (q to quit): ").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            raise SystemExit(0)
        if raw.lower() in ("q", "quit", ""):
            raise SystemExit(0)
        picked = _resolve_interactive_pick(
            raw,
            rows=rows,
            combined_by_id=combined_by_id,
            blocked_by_id=blocked_by_id,
            children_by_parent=children_by_parent,
            all_by_id=all_by_id,
        )
        if picked is not None:
            return picked
