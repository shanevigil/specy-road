"""What ``brainstorm promote`` will write: one :class:`Landing` per new node.

Split from ``brainstorm_promote`` (which writes them) for the file cap. Plain
promote makes one landing per accepted idea, under its ``target_parent`` or
the anchor; ``--by-cluster`` makes one per cluster lead and folds the rest of
the cluster in as alternatives; ``--min-recommendation`` drops weaker
verdicts first; ``--plan`` reads a YAML tree whose nodes link ideas by id.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from specy_road.bundled_scripts.brainstorm_session import (
    BrainstormError,
    BrainstormSession,
    Idea,
    PROMOTABLE_STATUSES,
)
from specy_road.bundled_scripts.roadmap_crud_dependency_ops import resolve_dependency_refs
from specy_road.bundled_scripts.roadmap_load import load_roadmap
from specy_road.bundled_scripts.roadmap_node_keys import new_node_key

#: Higher is stronger; an idea with no verdict ranks below ``park``.
RECOMMENDATION_RANK = {"strong": 3, "consider": 2, "park": 1}

PLAN_KEYS = ("ref", "parent", "type", "title", "acceptance", "dependencies", "ideas")


@dataclass
class Landing:
    """One node promote will write, and the ideas that point at it."""

    title: str
    #: An existing node's display id, the node_key of an earlier landing, or None (root).
    parent: str | None
    node_type: str
    #: The first seeds the sheet; every one is linked to the node.
    ideas: list[Idea] = field(default_factory=list)
    #: Same-cluster ideas folded into this node (``--by-cluster``); also linked.
    alternatives: list[Idea] = field(default_factory=list)
    acceptance: list[str] = field(default_factory=list)
    #: node_keys, already resolved.
    dependencies: list[str] = field(default_factory=list)
    node_key: str = field(default_factory=new_node_key)

    def linked(self) -> list[Idea]:
        return [*self.ideas, *self.alternatives]


def _accept_order_key(idea: Idea) -> tuple[int, str, str]:
    """Sort pending ideas by accept sequence, then decision time, then id."""
    dec = idea.decision or {}
    raw = dec.get("seq")
    try:
        seq = int(str(raw)) if raw not in (None, "") else 0
    except (TypeError, ValueError):
        seq = 0
    when = dec.get("decided_at") or dec.get("decided_date") or ""
    return (seq, when, idea.id)


def pending_ideas(session: BrainstormSession) -> list[Idea]:
    """Accepted ideas that have not been promoted yet."""
    return [i for i in session.ideas
            if i.status in PROMOTABLE_STATUSES and not i.promoted_node_key]


def _rank(idea: Idea) -> int:
    return RECOMMENDATION_RANK.get(idea.recommendation or "", 0)


def below_recommendation(ideas: list[Idea], minimum: str | None) -> list[Idea]:
    """The ideas ``--min-recommendation minimum`` leaves out."""
    if minimum is None:
        return []
    if minimum not in RECOMMENDATION_RANK:
        raise BrainstormError(f"--min-recommendation {minimum!r} not one of {', '.join(RECOMMENDATION_RANK)}")
    return [i for i in ideas if _rank(i) < RECOMMENDATION_RANK[minimum]]


def cluster_siblings(session: BrainstormSession, idea: Idea) -> list[Idea]:
    """Rejected or parked ideas from the same converge cluster."""
    if not idea.cluster_id:
        return []
    return [i for i in session.ideas
            if i.cluster_id == idea.cluster_id and i.id != idea.id and i.status in ("rejected", "parked")]


def idea_landings(todo: list[Idea], anchor: str | None, node_type: str, *,
                  by_cluster: bool = False) -> list[Landing]:
    """One landing per idea (in ``todo`` order), or per cluster lead with ``by_cluster``.

    A lead is the cluster's strongest verdict, the earlier accept on a tie; an
    idea without a cluster is its own lead. ``target_parent`` beats ``anchor``.
    """
    if not by_cluster:
        return [Landing(i.title, i.target_parent or anchor, node_type, ideas=[i]) for i in todo]
    groups: dict[str, list[Idea]] = {}
    for i in todo:
        groups.setdefault(i.cluster_id or f"\0{i.id}", []).append(i)
    leads = []
    for members in groups.values():
        lead = max(members, key=_rank)  # max keeps the first of equals: accept order
        leads.append(Landing(lead.title, lead.target_parent or anchor, node_type, ideas=[lead],
                             alternatives=[i for i in members if i is not lead]))
    return sorted(leads, key=lambda ln: todo.index(ln.ideas[0]))


def _read_plan(path: Path) -> list[Any]:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as e:
        raise BrainstormError(f"cannot read plan {path}: {e}") from e
    nodes = raw.get("nodes") if isinstance(raw, dict) else None
    if not isinstance(nodes, list) or not nodes:
        raise BrainstormError(f"plan {path}: expected a mapping with a non-empty `nodes:` list")
    return nodes


def _str_list(entry: dict, key: str, where: str) -> list[str]:
    value = entry.get(key) or []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list) or not all(isinstance(v, str) and v.strip() for v in value):
        raise BrainstormError(f"{where}: `{key}` must be a list of non-empty strings")
    return [v.strip() for v in value]


def _plan_entry(raw: Any, where: str) -> dict:
    if not isinstance(raw, dict):
        raise BrainstormError(f"{where}: each node must be a mapping")
    unknown = sorted(set(map(str, raw)) - set(PLAN_KEYS))
    if unknown:
        raise BrainstormError(f"{where}: unknown key(s) {', '.join(unknown)} (allowed: {', '.join(PLAN_KEYS)})")
    for key in ("ref", "parent", "type", "title"):
        if raw.get(key) is not None and not (isinstance(raw[key], str) and raw[key].strip()):
            raise BrainstormError(f"{where}: `{key}` must be a non-empty string")
    if not raw.get("title"):
        raise BrainstormError(f"{where}: `title` is required")
    return {k: (raw[k].strip() if isinstance(raw.get(k), str) else raw.get(k)) for k in PLAN_KEYS}


def _plan_ideas(session: BrainstormSession, ids: list[str], claimed: set[str], where: str) -> list[Idea]:
    out = []
    for ident in ids:
        idea = session.by_id(ident)
        if idea.status not in PROMOTABLE_STATUSES or idea.promoted_node_key:
            raise BrainstormError(f"{where}: idea {idea.id} is not an accepted, unpromoted idea")
        if idea.id in claimed:
            raise BrainstormError(f"{where}: idea {idea.id} is linked by an earlier plan node")
        claimed.add(idea.id)
        out.append(idea)
    return out


def _plan_dependencies(root: Path, refs: list[str], keys: dict[str, str], where: str) -> list[str]:
    """Plan refs map to the landings' node_keys; anything else must name a node on the roadmap."""
    try:
        existing = resolve_dependency_refs(root, [r for r in refs if r not in keys])
    except ValueError as e:
        raise BrainstormError(f"{where}: {e}") from e
    it = iter(existing)
    return [keys[r] if r in keys else next(it) for r in refs]


def plan_landings(root: Path, session: BrainstormSession, path: Path,
                  anchor: str | None, node_type: str) -> list[Landing]:
    """The plan's nodes in file order; a ``parent`` ref must name an earlier node."""
    node_ids = {n.get("id") for n in load_roadmap(root)["nodes"]}
    entries, keys, claimed = [], {}, set()
    for n, raw in enumerate(_read_plan(path), 1):
        where = f"plan {path.name} node {n}"
        entry = _plan_entry(raw, where)
        ref, parent = entry["ref"], entry["parent"]
        if ref and (ref in keys or ref in node_ids):
            raise BrainstormError(f"{where}: ref {ref!r} is already a plan ref or a roadmap node id")
        if parent and parent not in keys and parent not in node_ids:
            raise BrainstormError(f"{where}: parent {parent!r} is neither an earlier plan ref nor a roadmap node id")
        landing = Landing(entry["title"], keys.get(parent, parent) if parent else anchor,
                          entry["type"] or node_type,
                          ideas=_plan_ideas(session, _str_list(entry, "ideas", where), claimed, where),
                          acceptance=_str_list(entry, "acceptance", where))
        if ref:
            keys[ref] = landing.node_key
        entries.append((entry, where, landing))
    for entry, where, landing in entries:
        landing.dependencies = _plan_dependencies(root, _str_list(entry, "dependencies", where), keys, where)
    return [landing for _e, _w, landing in entries]


def select_landings(root: Path, session: BrainstormSession, anchor: str | None, node_type: str, *,
                    by_cluster: bool = False, min_recommendation: str | None = None,
                    plan: Path | None = None) -> list[Landing]:
    """What one promote call writes: ``plan``'s nodes, or the pending ideas in accept order."""
    if plan is not None:
        if by_cluster or min_recommendation:
            raise BrainstormError("--plan places every node itself; drop --by-cluster and --min-recommendation")
        return plan_landings(root, session, plan, anchor, node_type)
    todo = sorted(pending_ideas(session), key=_accept_order_key)
    weak = below_recommendation(todo, min_recommendation)
    return idea_landings([i for i in todo if i not in weak], anchor, node_type, by_cluster=by_cluster)
