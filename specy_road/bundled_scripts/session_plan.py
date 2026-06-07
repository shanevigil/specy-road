"""Read-only session-plan analysis for ``specy-road grind-session``.

Classifies roadmap leaves (ready / blocked / active / closed / gated) and lays
out **dependency waves** + **parallel batches** so an orchestrator can plan
sub-agent work without trial-and-error pickup:

* ``ready``    — deps satisfied, unclaimed: pickable *now* (same set/order as
  ``do-next-available-task`` would claim).
* ``blocked``  — unmet effective dependencies; each carries ``waiting_on``
  (display ids) and a ``reason`` (``dependency`` or ``gate``).
* ``active``   — already claimed (registry) or status *In Progress* (in flight).
* ``waves``    — leaves layered by dependency depth; wave *k* unlocks only once
  every leaf in waves ``< k`` is Complete. This is what lets an orchestrator
  avoid spawning a sub-agent for a not-yet-ready wave (e.g. ``M11.1`` while
  ``M10.5`` is still in flight).
* ``parallel_batches`` — per wave, the subset that is *ready and unclaimed*,
  i.e. the sets of independent leaves an orchestrator can dispatch in parallel,
  wave by wave.

Pure functions only: no git, no disk writes. Callers load the roadmap + registry
and pass them in.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from do_next_available import _available, _claimed_node_ids, _leaf_node_ids
from roadmap_layout import effective_dependency_keys, natural_id_sort_key
from specy_road.milestone_subtree import subtree_node_ids


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class BlockedLeaf:
    node_id: str
    codename: str
    waiting_on: list[str]
    reason: str  # "dependency" | "gate"


@dataclass
class Wave:
    index: int
    node_ids: list[str]


@dataclass
class SessionPlan:
    under: str | None
    ready: list[str]
    blocked: list[BlockedLeaf]
    active: list[str]
    closed: list[str]
    gated: list[str]
    gates_open: list[str]
    needs_codename: list[str]
    waves: list[Wave]
    parallel_batches: list[list[str]]
    totals: dict[str, int] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _status(node: dict) -> str:
    return (node.get("status") or "Not Started").lower()


def _sorted_ids(ids) -> list[str]:
    return sorted(ids, key=natural_id_sort_key)


def _scope_leaf_ids(nodes: list[dict], under: str | None) -> set[str]:
    leaves = _leaf_node_ids(nodes)
    if under:
        return leaves & subtree_node_ids(under, nodes)
    return leaves


def _unmet_dep_keys(
    node: dict,
    statuses_by_key: dict[str, str],
    eff: dict[str, set[str]],
) -> list[str]:
    nk = node.get("node_key")
    if not nk:
        return []
    return [
        d
        for d in eff.get(nk, set())
        if statuses_by_key.get(d, "") != "complete"
    ]


def _gate_keys(nodes: list[dict]) -> set[str]:
    return {
        n["node_key"]
        for n in nodes
        if n.get("type") == "gate" and n.get("node_key")
    }


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


def _classify(
    nodes: list[dict],
    reg: dict,
    *,
    under: str | None,
) -> dict:
    """Bucket scoped leaves into ready / blocked / active / closed / gated."""
    by_key = {n["node_key"]: n for n in nodes if n.get("node_key")}
    key_to_id = {n["node_key"]: n["id"] for n in nodes if n.get("node_key")}
    statuses_by_key = {
        n["node_key"]: _status(n) for n in nodes if n.get("node_key")
    }
    eff = effective_dependency_keys(nodes)
    gate_keys = _gate_keys(nodes)
    claimed = _claimed_node_ids(reg)
    scope = _scope_leaf_ids(nodes, under)

    ready_order = [n["id"] for n in _available(nodes, reg) if n["id"] in scope]
    ready_set = set(ready_order)

    buckets: dict[str, list] = {
        "ready": ready_order,
        "blocked": [],
        "active": [],
        "closed": [],
        "gated": [],
        "needs_codename": [],
    }
    for n in nodes:
        nid = n.get("id")
        if nid not in scope or n.get("type") == "gate":
            continue
        st = _status(n)
        if st in ("complete", "cancelled"):
            buckets["closed"].append(nid)
            continue
        if nid in ready_set:
            continue
        if nid in claimed or st == "in progress":
            buckets["active"].append(nid)
            continue
        if not n.get("codename"):
            buckets["needs_codename"].append(nid)
            continue
        unmet = _unmet_dep_keys(n, statuses_by_key, eff)
        if not unmet:
            # Deps met but not pickable for a reason already handled above; skip.
            continue
        waiting_on = _sorted_ids(
            key_to_id[d] for d in unmet if d in key_to_id
        )
        gate_blocked = any(d in gate_keys for d in unmet)
        leaf = BlockedLeaf(
            node_id=nid,
            codename=n.get("codename") or "",
            waiting_on=waiting_on,
            reason="gate" if gate_blocked else "dependency",
        )
        buckets["blocked"].append(leaf)
        if gate_blocked:
            buckets["gated"].append(nid)

    gates_open = _open_gates_blocking(nodes, eff, scope, gate_keys)
    return {
        "buckets": buckets,
        "by_key": by_key,
        "key_to_id": key_to_id,
        "statuses_by_key": statuses_by_key,
        "eff": eff,
        "gate_keys": gate_keys,
        "claimed": claimed,
        "scope": scope,
        "ready_set": ready_set,
        "gates_open": gates_open,
    }


def _open_gates_blocking(
    nodes: list[dict],
    eff: dict[str, set[str]],
    scope: set[str],
    gate_keys: set[str],
) -> list[str]:
    """Gate node ids (not Complete) that block at least one scoped leaf."""
    statuses = {n["node_key"]: _status(n) for n in nodes if n.get("node_key")}
    key_to_id = {n["node_key"]: n["id"] for n in nodes if n.get("node_key")}
    needed: set[str] = set()
    for n in nodes:
        if n.get("id") not in scope:
            continue
        nk = n.get("node_key")
        if not nk:
            continue
        for d in eff.get(nk, set()):
            if d in gate_keys and statuses.get(d, "") != "complete":
                needed.add(d)
    return _sorted_ids(key_to_id[k] for k in needed if k in key_to_id)


# ---------------------------------------------------------------------------
# Wave layering
# ---------------------------------------------------------------------------


def _compute_waves(nodes: list[dict], ctx: dict) -> list[Wave]:
    """Layer schedulable leaves by dependency depth (finish-to-start)."""
    buckets = ctx["buckets"]
    statuses_by_key = ctx["statuses_by_key"]
    eff = ctx["eff"]
    key_to_id = ctx["key_to_id"]
    gated = set(buckets["gated"])

    blocked_dep_ids = {
        b.node_id for b in buckets["blocked"] if b.reason == "dependency"
    }
    schedulable = (
        set(buckets["ready"]) | blocked_dep_ids | set(buckets["active"])
    ) - gated
    id_to_key = {
        n["id"]: n["node_key"]
        for n in nodes
        if n.get("node_key") and n["id"] in schedulable
    }
    complete_keys = {k for k, st in statuses_by_key.items() if st == "complete"}

    assigned: dict[str, int] = {}
    remaining = set(schedulable)
    wave_idx = 0
    while remaining:
        # node_keys of leaves already placed in an earlier wave.
        placed_keys = {
            id_to_key[i] for i in assigned if i in id_to_key
        }
        resolved_now = complete_keys | placed_keys
        layer = []
        for nid in remaining:
            nk = id_to_key.get(nid)
            unmet = [
                d
                for d in eff.get(nk, set())
                if statuses_by_key.get(d, "") != "complete"
            ] if nk else []
            # Schedulable iff every unmet dep is resolved by an earlier wave.
            if all(d in resolved_now for d in unmet):
                layer.append(nid)
        if not layer:
            break  # remaining depend on unschedulable nodes (gate/external)
        for nid in layer:
            assigned[nid] = wave_idx
            remaining.discard(nid)
        wave_idx += 1

    waves: list[Wave] = []
    max_wave = max(assigned.values(), default=-1)
    for k in range(max_wave + 1):
        ids = _sorted_ids(nid for nid, w in assigned.items() if w == k)
        waves.append(Wave(index=k, node_ids=ids))
    return waves


def _parallel_batches(waves: list[Wave], ready_set: set[str]) -> list[list[str]]:
    """Per wave, the ready+unclaimed leaves an orchestrator can dispatch now."""
    out: list[list[str]] = []
    for w in waves:
        dispatchable = [nid for nid in w.node_ids if nid in ready_set]
        if dispatchable:
            out.append(dispatchable)
    return out


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compute_session_plan(
    nodes: list[dict],
    reg: dict,
    *,
    under: str | None = None,
) -> SessionPlan:
    ctx = _classify(nodes, reg, under=under)
    buckets = ctx["buckets"]
    waves = _compute_waves(nodes, ctx)
    batches = _parallel_batches(waves, ctx["ready_set"])
    plan = SessionPlan(
        under=under,
        ready=list(buckets["ready"]),
        blocked=list(buckets["blocked"]),
        active=_sorted_ids(buckets["active"]),
        closed=_sorted_ids(buckets["closed"]),
        gated=_sorted_ids(buckets["gated"]),
        gates_open=list(ctx["gates_open"]),
        needs_codename=_sorted_ids(buckets["needs_codename"]),
        waves=waves,
        parallel_batches=batches,
    )
    plan.totals = {
        "ready": len(plan.ready),
        "blocked": len(plan.blocked),
        "active": len(plan.active),
        "closed": len(plan.closed),
        "gated": len(plan.gated),
        "gates_open": len(plan.gates_open),
        "needs_codename": len(plan.needs_codename),
        "waves": len(plan.waves),
    }
    return plan


def session_plan_to_dict(plan: SessionPlan) -> dict:
    """JSON-serializable view of a :class:`SessionPlan`."""
    return {
        "under": plan.under,
        "ready": list(plan.ready),
        "blocked": [asdict(b) for b in plan.blocked],
        "active": list(plan.active),
        "closed": list(plan.closed),
        "gated": list(plan.gated),
        "gates_open": list(plan.gates_open),
        "needs_codename": list(plan.needs_codename),
        "waves": [asdict(w) for w in plan.waves],
        "parallel_batches": [list(b) for b in plan.parallel_batches],
        "totals": dict(plan.totals),
    }
