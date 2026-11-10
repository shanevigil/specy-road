"""One index over the merged roadmap graph: the single answer to every graph query.

Pickup, the grind plan, why-blocked, the brief and the digest each used to build
their own ``node_key -> node`` maps, effective-dependency maps and "is this
dependency Complete" checks. They agreed by test, not by construction. They now
ask :class:`RoadmapIndex` instead:

* :attr:`~RoadmapIndex.by_id` and :attr:`~RoadmapIndex.by_key` — node lookup by
  display id and by stable ``node_key``.
* :attr:`~RoadmapIndex.status` — lowercased **rollup** status per ``node_key``,
  which is what dependency satisfaction reads (a phase's own ``status`` is
  bookkeeping nothing updates when its last leaf closes).
* :attr:`~RoadmapIndex.effective_dependencies` — a node's explicit dependencies
  plus every dependency inherited from an ancestor, limited to live keys.
* :meth:`~RoadmapIndex.unmet` — the effective dependencies not yet Complete.
* :meth:`~RoadmapIndex.ready` — leaves pickup may claim, in outline order.

Every map is computed on first use, so a caller that only needs effective
dependencies does not pay for the rollup or the outline walk. The index reads
no git and no files: callers load the roadmap and registry and pass them in.
"""

from __future__ import annotations

from functools import cached_property
from typing import Iterable, Mapping

from specy_road.bundled_scripts.roadmap_load import compute_rollup_status
from specy_road.milestone_subtree import structural_leaf_ids
from specy_road.node_kinds import is_pickable

#: Own statuses that take a leaf out of pickup whatever its dependencies say.
CLOSED_STATUSES = ("complete", "cancelled")


class RoadmapIndex:
    """Lookups and readiness over one list of roadmap nodes.

    ``status_overrides`` (keyed by ``node_key``) replaces own statuses *before*
    the rollup is computed, so a leaf whose feature branch is already Complete
    also counts toward its ancestors' rollup. ``claimed`` holds the display ids
    the claim registry already hands to someone; :meth:`ready` leaves them out.
    """

    def __init__(
        self,
        nodes: list[dict],
        *,
        status_overrides: Mapping[str, str] | None = None,
        claimed: Iterable[str] = (),
    ) -> None:
        self.nodes = nodes
        self.status_overrides = dict(status_overrides or {})
        self.claimed = frozenset(claimed)

    @cached_property
    def by_id(self) -> dict[str, dict]:
        """Node by display id."""
        return {n["id"]: n for n in self.nodes if isinstance(n.get("id"), str) and n["id"]}

    @cached_property
    def by_key(self) -> dict[str, dict]:
        """Node by stable ``node_key`` (the key dependencies reference)."""
        return {
            n["node_key"]: n
            for n in self.nodes
            if isinstance(n.get("node_key"), str) and n["node_key"]
        }

    @cached_property
    def status(self) -> dict[str, str]:
        """``node_key`` -> lowercased rollup status, after ``status_overrides``."""
        own_by_id: dict[str, str] = {}
        for key, value in self.status_overrides.items():
            node = self.by_key.get(key)
            if node is not None and isinstance(node.get("id"), str):
                own_by_id[node["id"]] = value or ""
        rollup = compute_rollup_status(self.nodes, own_by_id or None)
        return {
            key: (rollup.get(node.get("id", ""), node.get("status") or "") or "").lower()
            for key, node in self.by_key.items()
        }

    @cached_property
    def effective_dependencies(self) -> dict[str, set[str]]:
        """``node_key`` -> explicit dependencies on the node and on every ancestor.

        Keys absent from the live graph are dropped. That is right for readiness:
        an archived dependency is Complete, so it is satisfied.
        """
        eff: dict[str, set[str]] = {}
        for node_key, node in self.by_key.items():
            acc: set[str] = set()
            cur: dict | None = node
            while cur:
                acc.update(d for d in cur.get("dependencies") or [] if d in self.by_key)
                parent_id = cur.get("parent_id")
                cur = self.by_id.get(parent_id) if parent_id else None
            eff[node_key] = acc
        return eff

    @cached_property
    def leaf_ids(self) -> set[str]:
        """Display ids of nodes that parent no other node."""
        return structural_leaf_ids(self.nodes)

    @cached_property
    def outline_position(self) -> dict[str, int]:
        """Display id -> pre-order outline index (siblings by ``sibling_order``, then id)."""
        # Imported here: roadmap_layout answers its dependency maps from this index.
        from specy_road.bundled_scripts.roadmap_layout import ordered_tree_rows

        return {node["id"]: i for i, (node, _depth) in enumerate(ordered_tree_rows(self.nodes))}

    def unmet(self, node: dict, statuses: Mapping[str, str] | None = None) -> list[str]:
        """Effective dependency keys of ``node`` that are not Complete, sorted.

        ``statuses`` replaces :attr:`status` for one question, such as "would
        this be blocked on the integration branch alone?".
        """
        node_key = node.get("node_key")
        if not node_key:
            return []
        current = self.status if statuses is None else statuses
        return sorted(
            (d for d in self.effective_dependencies.get(node_key, set())
             if current.get(d, "") != "complete"),
            key=str,
        )

    def ready(self) -> list[dict]:
        """Leaves pickup may claim, in outline order.

        A ready leaf is a pickable (non-gate) leaf with a codename, not claimed,
        not Complete or Cancelled, whose effective dependencies are all
        Complete. Pickup's tiers (Blocked first, then MR-rejected, then the
        rest, skipping In Progress) order and filter this set further.
        """
        tail = len(self.outline_position)
        found = [
            n for n in self.nodes
            if n.get("id") in self.leaf_ids
            and is_pickable(n)
            and n.get("codename")
            and n["id"] not in self.claimed
            and (n.get("status") or "Not Started").lower() not in CLOSED_STATUSES
            and not self.unmet(n)
        ]
        return sorted(found, key=lambda n: self.outline_position.get(n["id"], tail))
