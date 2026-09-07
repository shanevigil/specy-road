"""Answer two questions about one node without computing a whole session plan.

``grind-session --plan`` already knows why every leaf is stuck and which gates
need a human, but reading either answer meant rendering the entire plan and
picking through it. These are the same computations, scoped to the question
being asked.

The dependency walk here is **transitive**, which is the part ``--plan`` does not
give you. ``BlockedLeaf.waiting_on`` lists a node's immediate unmet dependencies;
the useful answer to "why is this blocked" is usually two or three hops away, at
whatever is not moving at the bottom of the chain.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from specy_road.bundled_scripts.do_next_available import _claimed_node_ids, _statuses_by_node_key
from specy_road.bundled_scripts.roadmap_layout import effective_dependency_keys, natural_id_sort_key
from specy_road.milestone_subtree import structural_leaf_ids, subtree_node_ids
from specy_road.node_kinds import is_gate

#: Cap on how deep the transitive walk reports. Chains longer than this are
#: real but unreadable, and the leading hops are the actionable ones.
MAX_DEPTH = 6


@dataclass
class DependencyNode:
    """One unmet dependency, plus whatever it is itself waiting on."""

    node_id: str
    node_key: str
    title: str
    status: str
    is_gate: bool
    claimed_by: str | None
    waiting_on: list["DependencyNode"] = field(default_factory=list)


@dataclass
class Explanation:
    node_id: str
    title: str
    state: str  # blocked | gated | ready | active | closed | needs_codename | unknown
    summary: str
    waiting_on: list[DependencyNode] = field(default_factory=list)


@dataclass
class OpenGate:
    node_id: str
    title: str
    status: str
    blocks: list[str]


def _by_id(nodes: list[dict]) -> dict[str, dict]:
    return {n["id"]: n for n in nodes if n.get("id")}


def _claim_branches(reg: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    for entry in reg.get("entries") or []:
        node_id, branch = entry.get("node_id"), entry.get("branch")
        if node_id and branch and node_id not in out:
            out[node_id] = branch
    return out


def _unmet(node_key: str, eff: dict[str, set[str]], statuses: dict[str, str]) -> list[str]:
    return sorted(
        (d for d in eff.get(node_key, set()) if statuses.get(d, "") != "complete"),
        key=str,
    )


def _walk(
    node_key: str,
    ctx: dict,
    depth: int,
    seen: set[str],
) -> list[DependencyNode]:
    """Unmet dependencies of ``node_key``, each with its own unmet chain.

    ``seen`` guards against a dependency cycle. ``validate`` rejects cycles, but
    this command is most often run *because* the graph is in a strange state.
    """
    if depth > MAX_DEPTH:
        return []
    out: list[DependencyNode] = []
    for key in _unmet(node_key, ctx["eff"], ctx["statuses"]):
        node = ctx["by_key"].get(key)
        if node is None or key in seen:
            continue
        nested = _walk(key, ctx, depth + 1, seen | {key})
        out.append(
            DependencyNode(
                node_id=node["id"],
                node_key=key,
                title=str(node.get("title") or ""),
                status=str(node.get("status") or "Not Started"),
                is_gate=is_gate(node.get("type")),
                claimed_by=ctx["claims"].get(node["id"]),
                waiting_on=nested,
            )
        )
    out.sort(key=lambda d: natural_id_sort_key(d.node_id))
    return out


def _context(nodes: list[dict], reg: dict) -> dict:
    return {
        "by_key": {n["node_key"]: n for n in nodes if n.get("node_key")},
        "eff": effective_dependency_keys(nodes),
        "statuses": _statuses_by_node_key(nodes),
        "claims": _claim_branches(reg),
    }


def _state_without_dependencies(
    node: dict, claimed: set[str], leaves: set[str]
) -> tuple[str, str] | None:
    """The answer when the graph, not a dependency, is what stops pickup."""
    node_id = node["id"]
    status = str(node.get("status") or "Not Started").lower()
    if status in ("complete", "cancelled"):
        return "closed", f"{node_id} is {node.get('status')}; there is nothing to pick up."
    if is_gate(node.get("type")):
        return "gated", (
            f"{node_id} is a gate node. Gates are never auto-picked; clear it with "
            "specy-road set-gate-status."
        )
    if node_id in claimed or status == "in progress":
        return "active", f"{node_id} is already in flight."
    if node_id not in leaves:
        # Checked before the codename, or a parent reports the codename it does
        # not need instead of the reason it was never pickable.
        return "container", (
            f"{node_id} has children, so it is never picked up directly — it is a "
            "context container whose status rolls up from its leaves. Ask about "
            "one of its leaves, or scope a plan with "
            f"specy-road grind-session --plan --under {node_id}."
        )
    if not node.get("codename"):
        return "needs_codename", (
            f"{node_id} has no codename, so it cannot be claimed. Set one with "
            f"specy-road edit-node {node_id} --set codename=<slug>."
        )
    return None


def explain(nodes: list[dict], reg: dict, node_id: str) -> Explanation:
    """Why ``node_id`` is not pickable — or that it is."""
    node = _by_id(nodes).get(node_id)
    if node is None:
        return Explanation(node_id, "", "unknown", f"no node with id {node_id}.")
    title = str(node.get("title") or "")
    ctx = _context(nodes, reg)
    early = _state_without_dependencies(
        node, _claimed_node_ids(reg), structural_leaf_ids(nodes)
    )
    if early is not None:
        state, summary = early
        if state == "active" and ctx["claims"].get(node_id):
            summary += f" Claimed on {ctx['claims'][node_id]}."
        return Explanation(node_id, title, state, summary)

    chain = _walk(node.get("node_key") or "", ctx, 0, {node.get("node_key") or ""})
    if not chain:
        return Explanation(
            node_id, title, "ready",
            f"{node_id} is not blocked — every dependency is Complete and nothing "
            "has claimed it.",
        )
    gate_hit = any(d.is_gate for d in chain)
    return Explanation(
        node_id, title,
        "gated" if gate_hit else "blocked",
        f"{node_id} is waiting on {len(chain)} unmet dependency/dependencies.",
        waiting_on=chain,
    )


def open_gates(nodes: list[dict], under: str | None = None) -> list[OpenGate]:
    """Gate nodes that are not Complete, with the nodes each one holds back.

    Scoped by ``under`` on the **blocked** side, not the gate side: the question
    is "what is stopping work in this phase", and a phase is routinely held by a
    gate that lives somewhere else in the graph.
    """
    ctx = _context(nodes, {})
    scope = subtree_node_ids(under, nodes) if under else None
    blocks: dict[str, list[str]] = {}
    for n in nodes:
        node_id, node_key = n.get("id"), n.get("node_key")
        if not node_key or (scope is not None and node_id not in scope):
            continue
        for key in _unmet(node_key, ctx["eff"], ctx["statuses"]):
            dep = ctx["by_key"].get(key)
            if dep is not None and is_gate(dep.get("type")):
                blocks.setdefault(dep["id"], []).append(node_id)
    gates = [
        OpenGate(
            node_id=n["id"],
            title=str(n.get("title") or ""),
            status=str(n.get("status") or "Not Started"),
            blocks=sorted(blocks.get(n["id"], []), key=natural_id_sort_key),
        )
        for n in nodes
        if is_gate(n.get("type"))
        and str(n.get("status") or "").lower() != "complete"
        and (scope is None or n["id"] in blocks)
    ]
    gates.sort(key=lambda g: natural_id_sort_key(g.node_id))
    return gates
