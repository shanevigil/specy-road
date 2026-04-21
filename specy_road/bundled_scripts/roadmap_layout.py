"""Pure roadmap layout helpers (dependency depth, tree order, edges) — no Plotly."""

from __future__ import annotations

import re


def _digit_run_to_int(run: str) -> int:
    """Parse an ASCII digit run for natural id ordering (hook for tests / rare bases)."""
    return int(run, 10)


def natural_id_sort_key(nid: str) -> tuple[tuple[int, int | str], ...]:
    """
    Sort key for a display ``id``: digit runs compare numerically; other runs compare
    as strings. If a digit run cannot be parsed (e.g. some Unicode digits), fall back
    to a single-string lexical key ``((1, nid),)`` so ordering matches plain ``nid``.
    """
    if not isinstance(nid, str):
        return ((1, str(nid)),)
    if not nid:
        return ((1, nid),)
    parts = re.findall(r"\d+|\D+", nid)
    if not parts:
        return ((1, nid),)
    out: list[tuple[int, int | str]] = []
    for p in parts:
        if p.isdigit():
            try:
                out.append((0, _digit_run_to_int(p)))
            except ValueError:
                return ((1, nid),)
        else:
            out.append((1, p))
    return tuple(out)


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


_MAX_DEP_STEP_ITERS = 1000


def _outline_children_map(nodes: list[dict]) -> dict[str | None, list[str]]:
    by_id = {n["id"]: n for n in nodes}
    children: dict[str | None, list[str]] = {}
    for n in nodes:
        pid = n.get("parent_id")
        if pid is not None and pid not in by_id:
            pid = None
        children.setdefault(pid, []).append(n["id"])
    for lst in children.values():
        lst.sort(key=lambda nid: sibling_sort_key(nid, by_id))
    return children


def _outline_post_order_ids(nodes: list[dict]) -> list[str]:
    """Outline post-order (children before parent); orphans appended like ``ordered_tree_rows``."""
    children = _outline_children_map(nodes)
    post: list[str] = []

    def dfs(nid: str) -> None:
        for cid in children.get(nid, []):
            dfs(cid)
        post.append(nid)

    for rid in children.get(None, []):
        dfs(rid)
    placed = set(post)
    for n in sorted(nodes, key=lambda x: natural_id_sort_key(x["id"])):
        if n["id"] not in placed:
            post.append(n["id"])
    return post


def compute_dependency_steps(
    nodes: list[dict],
) -> tuple[dict[str, int], dict[str, int]]:
    """
    Dependency **start** step (0-based) and **span** (integer steps, ≥ 1) per display ``id``.

    * **Finish-to-start:** a node starts at ``max(end(dependency))`` over effective deps
      (same inheritance as ``effective_dependency_keys``).
    * **Outline rollup:** ``end = max(start + 1, max(end(child)))`` for direct outline children,
      post-order so children are finalized first.
    * Values converge by fixed-point iteration (valid roadmaps are DAGs; cap for safety).
    """
    eff = effective_dependency_keys(nodes)
    key_to_id = {n["node_key"]: n["id"] for n in nodes if n.get("node_key")}
    by_id = {n["id"]: n for n in nodes}
    ids_with_key = {n["id"] for n in nodes if n.get("node_key")}
    children = _outline_children_map(nodes)
    post_order = [nid for nid in _outline_post_order_ids(nodes) if nid in ids_with_key]

    start: dict[str, int] = {i: 0 for i in ids_with_key}
    end: dict[str, int] = {i: 0 for i in ids_with_key}

    for _ in range(_MAX_DEP_STEP_ITERS):
        prev_s = start.copy()
        prev_e = end.copy()
        for nid in ids_with_key:
            n = by_id[nid]
            nk = n.get("node_key")
            if not nk:
                continue
            dep_ids = [key_to_id[d] for d in eff.get(nk, set()) if d in key_to_id]
            if not dep_ids:
                start[nid] = 0
            else:
                start[nid] = max(prev_e.get(did, 0) for did in dep_ids)
        for nid in post_order:
            n = by_id[nid]
            nk = n.get("node_key")
            if not nk:
                continue
            chs = [c for c in children.get(nid, []) if c in ids_with_key]
            base = start[nid] + 1
            if chs:
                end[nid] = max(base, max(end.get(c, 0) for c in chs))
            else:
                end[nid] = base
        if start == prev_s and end == prev_e:
            break

    span = {nid: max(1, end[nid] - start[nid]) for nid in start}
    return start, span


def compute_depths(nodes: list[dict]) -> dict[str, int]:
    """0-based dependency **start** step (finish-to-start + outline rollup); keyed by display ``id``."""
    starts, _ = compute_dependency_steps(nodes)
    return starts


def sibling_sort_key(
    nid: str, by_id: dict[str, dict]
) -> tuple[int, tuple[tuple[int, int | str], ...]]:
    """Siblings sort by ``(sibling_order, natural_id_sort_key(id))``."""
    n = by_id[nid]
    o = n.get("sibling_order")
    orderv = o if isinstance(o, int) else 0
    return (orderv, natural_id_sort_key(nid))


def ordered_tree_rows(nodes: list[dict]) -> list[tuple[dict, int]]:
    """
    Parent/child order: roots first, then DFS children.
    Siblings sort by ``(sibling_order, natural numeric id)``; tie-break digit segments
    numerically (not raw string order). Orphans attach at end.
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
    for n in sorted(nodes, key=lambda x: natural_id_sort_key(x["id"])):
        if n["id"] not in placed:
            out.append((n, 0))
    return out


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
            "explicit": sorted(
                (key_to_id[k] for k in explicit_keys if k in key_to_id),
                key=natural_id_sort_key,
            ),
            "inherited": sorted(
                (key_to_id[k] for k in inherited_keys if k in key_to_id),
                key=natural_id_sort_key,
            ),
        }
    return out
