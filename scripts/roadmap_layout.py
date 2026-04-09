"""Pure roadmap layout helpers (dependency depth, tree order, edges) — no Plotly."""

from __future__ import annotations


def compute_depths(nodes: list[dict]) -> dict[str, int]:
    by_id = {n["id"]: n for n in nodes}
    memo: dict[str, int] = {}

    def depth(nid: str) -> int:
        if nid in memo:
            return memo[nid]
        deps = by_id[nid].get("dependencies") or []
        if not deps:
            memo[nid] = 0
            return 0
        d = 1 + max(depth(x) for x in deps)
        memo[nid] = d
        return d

    for n in nodes:
        depth(n["id"])
    return memo


def sibling_sort_key(nid: str, by_id: dict[str, dict]) -> tuple[int, str]:
    n = by_id[nid]
    o = n.get("sibling_order")
    if isinstance(o, int):
        return (o, nid)
    return (0, nid)


def ordered_tree_rows(nodes: list[dict]) -> list[tuple[dict, int]]:
    """
    Parent/child order: roots first, then DFS children.
    Siblings sort by (sibling_order, id). Returns (node, depth) with depth 0 for roots.
    Orphans attach at end.
    """
    by_id = {n["id"]: n for n in nodes}
    children: dict[str | None, list[str]] = {}
    for n in nodes:
        pid = n.get("parent_id")
        if pid is not None and pid not in by_id:
            pid = None
        children.setdefault(pid, []).append(n["id"])
    for lst in children.values():
        lst.sort(key=lambda nid: sibling_sort_key(nid, by_id))
    out: list[tuple[dict, int]] = []

    def dfs(nid: str, depth_val: int) -> None:
        node = by_id[nid]
        out.append((node, depth_val))
        for cid in children.get(nid, []):
            dfs(cid, depth_val + 1)

    for rid in children.get(None, []):
        dfs(rid, 0)
    placed = {t[0]["id"] for t in out}
    for n in sorted(nodes, key=lambda x: x["id"]):
        if n["id"] not in placed:
            out.append((n, 0))
    return out


def dependency_edges(nodes: list[dict]) -> list[tuple[str, str]]:
    """Edges (dependency_id, dependent_id) for graph overlays."""
    ids = {n["id"] for n in nodes}
    edges: list[tuple[str, str]] = []
    for n in nodes:
        for dep in n.get("dependencies") or []:
            if dep in ids:
                edges.append((dep, n["id"]))
    return edges
