"""Pure roadmap layout helpers (dependency depth, tree order, edges) — no Plotly."""

from __future__ import annotations


def effective_dependency_keys(nodes: list[dict]) -> dict[str, set[str]]:
    """
    For each ``node_key``, union of explicit ``dependencies`` on the node and on
    every ancestor (inheritance at group level).
    """
    by_key = {n["node_key"]: n for n in nodes if n.get("node_key")}
    by_id = {n["id"]: n for n in nodes}
    eff: dict[str, set[str]] = {}
    for n in nodes:
        nk = n.get("node_key")
        if not nk:
            continue
        acc: set[str] = set()
        cur: dict | None = n
        while cur:
            for d in cur.get("dependencies") or []:
                if d in by_key:
                    acc.add(d)
            pid = cur.get("parent_id")
            if not pid:
                break
            cur = by_id.get(pid)
        eff[nk] = acc
    return eff


def compute_depths(nodes: list[dict]) -> dict[str, int]:
    """Dependency step depth using effective (inherited) dependencies; keyed by display ``id``."""
    eff = effective_dependency_keys(nodes)
    memo: dict[str, int] = {}

    def depth(nk: str) -> int:
        if nk in memo:
            return memo[nk]
        deps = eff.get(nk, set())
        if not deps:
            memo[nk] = 0
            return 0
        d = 1 + max(depth(x) for x in deps)
        memo[nk] = d
        return d

    out: dict[str, int] = {}
    for n in nodes:
        nk = n.get("node_key")
        if nk:
            out[n["id"]] = depth(nk)
    return out


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
    """Edges (dependency_id, dependent_id) for graph overlays; deps are ``node_key`` values."""
    key_to_id = {n["node_key"]: n["id"] for n in nodes if n.get("node_key")}
    edges: list[tuple[str, str]] = []
    for n in nodes:
        for dep in n.get("dependencies") or []:
            tid = key_to_id.get(dep)
            if tid:
                edges.append((tid, n["id"]))
    return edges


def dependency_edges_detailed(
    nodes: list[dict],
) -> list[dict[str, str]]:
    """
    Directed edges for dependency overlays using **effective** (inherited + explicit) deps.

    Each item is ``{"from": dep_display_id, "to": dependent_display_id, "kind": "explicit"|"inherited"}``.
    """
    eff = effective_dependency_keys(nodes)
    key_to_id = {n["node_key"]: n["id"] for n in nodes if n.get("node_key")}
    out: list[dict[str, str]] = []
    for n in nodes:
        nk = n.get("node_key")
        if not nk:
            continue
        explicit_keys = set(n.get("dependencies") or [])
        for dk in eff.get(nk, set()):
            dep_id = key_to_id.get(dk)
            if not dep_id:
                continue
            kind = "inherited" if dk not in explicit_keys else "explicit"
            out.append(
                {
                    "from": dep_id,
                    "to": n["id"],
                    "kind": kind,
                }
            )
    return out


def dependency_inheritance_display(
    nodes: list[dict],
) -> dict[str, dict[str, list[str]]]:
    """
    Per display ``id``: dependency display ids that are explicit on the node vs
    inherited from ancestors (effective minus explicit).
    """
    eff = effective_dependency_keys(nodes)
    key_to_id = {n["node_key"]: n["id"] for n in nodes if n.get("node_key")}
    out: dict[str, dict[str, list[str]]] = {}
    for n in nodes:
        nk = n.get("node_key")
        if not nk:
            continue
        explicit_keys = set(n.get("dependencies") or [])
        inherited_keys = eff.get(nk, set()) - explicit_keys
        nid = n["id"]
        out[nid] = {
            "explicit": sorted(key_to_id[k] for k in explicit_keys if k in key_to_id),
            "inherited": sorted(key_to_id[k] for k in inherited_keys if k in key_to_id),
        }
    return out
