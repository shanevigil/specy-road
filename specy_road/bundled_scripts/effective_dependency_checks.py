"""Dependency cycles, and serialization, on the graph the scheduler waits on.

``cycle_check`` walks explicit ``dependencies`` only. ``effective_cycle_check``
adds what ``session_plan`` also waits on: dependencies inherited from ancestors
(``effective_dependency_keys``) and, for a dependency on a group, every leaf
under it. ``newly_waiting_suffix`` reports the leaves an ``add-dependency`` on
a group newly serializes.
"""

from __future__ import annotations

import sys

from specy_road.bundled_scripts.roadmap_layout import effective_dependency_keys, ordered_tree_rows
from specy_road.milestone_subtree import leaf_ids_under_parent
from specy_road.node_kinds import is_gate


def cycle_check(nodes: list[dict]) -> None:
    """DFS cycle detection on dependency edges."""
    by_key = {n["node_key"]: n for n in nodes}
    visited: set[str] = set()
    stack: set[str] = set()

    def visit(nk: str) -> None:
        if nk in stack:
            n = by_key.get(nk, {})
            msg = (
                f"roadmap: dependency cycle involving "
                f"{n.get('id', nk)}"
            )
            print(msg, file=sys.stderr)
            raise SystemExit(1)
        if nk in visited:
            return
        stack.add(nk)
        for dep in by_key[nk].get("dependencies") or []:
            if dep in by_key:
                visit(dep)
        stack.remove(nk)
        visited.add(nk)

    for nk in by_key:
        if nk not in visited:
            visit(nk)


def _scheduling_edges(nodes: list[dict]) -> dict[str, dict[str, str]]:
    """Per node_key, what it waits on and why, in outline order.

    A node waits on its effective dependencies (its own plus every ancestor's,
    as ``effective_dependency_keys`` computes them), and a group completes only
    when its children do, so a group waits on each child. Following the
    parent-child edges from a dependency target reaches every leaf under it,
    which is what ``session_plan`` waits on. Each edge keeps its first origin:
    ``""`` for an explicit dependency, else the text naming where it comes from.
    """
    rows = [n for n, _ in ordered_tree_rows(nodes) if n.get("node_key")]
    by_id = {n["id"]: n for n in rows}
    pos = {n["node_key"]: i for i, n in enumerate(rows)}
    edges: dict[str, dict[str, str]] = {}
    for n in rows:
        nk = n["node_key"]
        out: dict[str, str] = {}
        for d in n.get("dependencies") or []:
            out.setdefault(d, "")
        anc = by_id.get(n.get("parent_id") or "")
        while anc is not None:
            for d in anc.get("dependencies") or []:
                if d in pos:
                    dep_id = rows[pos[d]]["id"]
                    out.setdefault(d, f"inherited from {anc['id']}, which depends on {dep_id}")
            anc = by_id.get(anc.get("parent_id") or "")
        edges[nk] = out
    for n in rows:
        parent = by_id.get(n.get("parent_id") or "")
        if parent is not None:
            edges[parent["node_key"]].setdefault(
                n["node_key"],
                f"parent-child rollup: {parent['id']} completes when its child {n['id']} does",
            )
    return {
        nk: {d: out[d] for d in sorted((d for d in out if d in pos), key=pos.__getitem__)}
        for nk, out in edges.items()
    }


def _inherited_self_edge(nodes: list[dict]) -> tuple[str, str] | None:
    """The first node (outline order) whose ancestor depends on it, with that ancestor."""
    by_id = {n["id"]: n for n in nodes}
    for n, _ in ordered_tree_rows(nodes):
        anc = by_id.get(n.get("parent_id") or "")
        while anc is not None:
            if n.get("node_key") in (anc.get("dependencies") or []):
                return n["id"], anc["id"]
            anc = by_id.get(anc.get("parent_id") or "")
    return None


def _first_cycle(edges: dict[str, dict[str, str]]) -> list[str] | None:
    """The first cycle an iterative DFS meets, as node_keys ``[a, ..., a]``."""
    done: set[str] = set()
    for start in edges:
        if start in done:
            continue
        path = [start]
        on_path = {start}
        iters = [iter(edges[start])]
        while iters:
            nxt = next(iters[-1], None)
            if nxt is None:
                iters.pop()
                done.add(path[-1])
                on_path.discard(path.pop())
            elif nxt in on_path:
                return path[path.index(nxt):] + [nxt]
            elif nxt not in done:
                path.append(nxt)
                on_path.add(nxt)
                iters.append(iter(edges[nxt]))
    return None


def effective_cycle_check(nodes: list[dict]) -> None:
    """Cycle detection on the scheduling graph (inherited and group dependencies).

    Runs after :func:`cycle_check`, so a cycle reported here goes through at
    least one derived edge; each derived edge on the path is printed with the
    explicit dependency or parent-child rollup edge it comes from.
    """
    self_edge = _inherited_self_edge(nodes)
    if self_edge is not None:
        print(f"roadmap: inherited self-edge {self_edge[0]} via {self_edge[1]}", file=sys.stderr)
        raise SystemExit(1)
    edges = _scheduling_edges(nodes)
    cycle = _first_cycle(edges)
    if cycle is None:
        return
    key_to_id = {n["node_key"]: n["id"] for n in nodes if n.get("node_key")}
    ids = [key_to_id[k] for k in cycle]
    print(f"roadmap: dependency cycle: {' -> '.join(ids)}", file=sys.stderr)
    for i, (a, b) in enumerate(zip(cycle, cycle[1:])):
        origin = edges[a][b]
        if origin:
            print(f"  {ids[i]} -> {ids[i + 1]}: {origin}", file=sys.stderr)
    raise SystemExit(1)


def newly_waiting_suffix(nodes: list[dict], node_id: str, dep_key: str) -> str:
    """What ``add-dependency`` prints after its ``[ok]`` line: the leaves it serializes.

    ``nodes`` is the graph before the edit. A descendant leaf of ``node_id``
    counts when it is not a gate, not Complete, and does not already depend on
    ``dep_key`` (effectively). ``""`` when none does, or when the prerequisite
    is Complete or archived (archived work is Complete); otherwise a newline and
    ``N descendant leaves now wait on <dep id>: <up to 5 ids in outline order>``.
    """
    dep = next((n for n in nodes if n.get("node_key") == dep_key), None)
    if dep is None or (dep.get("rollup_status") or dep.get("status")) == "Complete":
        return ""
    eff = effective_dependency_keys(nodes)
    leaves = leaf_ids_under_parent(node_id, nodes) - {node_id}
    waiting = [
        n["id"]
        for n, _ in ordered_tree_rows(nodes)
        if n["id"] in leaves
        and not is_gate(n.get("type"))
        and n.get("status") != "Complete"
        and dep_key not in eff.get(n.get("node_key"), set())
    ]
    if not waiting:
        return ""
    return f"\n{len(waiting)} descendant leaves now wait on {dep['id']}: {', '.join(waiting[:5])}"
