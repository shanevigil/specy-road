"""Keep a claim's touch zones in step when ``edit-node`` changes the node's.

Pickup snapshots a leaf's zones into its ``roadmap/registry.yaml`` row, and the
review packet and the finish implementation check both read that row before the
node. Widening a claimed leaf's zones with ``edit-node`` therefore changed
nothing either of them saw: the packet kept flagging files that were now in
zone and finish could refuse. ``move-node`` already rewrites claim zones (by
renumbered path segment); this does the same for an edit, which replaces the
list outright, so the two share the registry and not the rewrite.

The registry write rides inside the edit's transaction: it lands before the
chunk write, so the edit's one validation sees both, and it is rolled back when
that write is rejected.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

from specy_road.bundled_scripts.roadmap_chunk_atomic import AtomicWritePlan
from specy_road.registry_yaml import dump_registry_text, read_registry, registry_path


def rewrite_claim_zones(entries: list, node_id: str, zones: list) -> list[str]:
    """Set ``touch_zones`` to ``zones`` on every row claiming ``node_id``.

    Returns the codenames of the rows that changed.
    """
    changed = []
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("node_id") != node_id:
            continue
        if entry.get("touch_zones") != zones:
            entry["touch_zones"] = list(zones)
            changed.append(str(entry.get("codename") or node_id))
    return changed


@contextmanager
def claim_zones_following(
    root: Path,
    node_id: str,
    zones: list | None,
    *,
    notify: Callable[[str], None] | None = None,
) -> Iterator[None]:
    """Write the claim rewrite, run the body, and undo the rewrite if it raises.

    ``zones`` is ``None`` when the edit did not set ``touch_zones``; the
    registry is then left alone.
    """
    path = registry_path(root)
    doc = read_registry(path) if zones is not None else {}
    entries = doc.get("entries") if isinstance(doc, dict) else None
    changed = rewrite_claim_zones(entries, node_id, zones) if isinstance(entries, list) else []
    if not changed:
        yield
        return
    plan = AtomicWritePlan(root)
    plan.stage_text(path, dump_registry_text(doc))
    plan.write()
    try:
        yield
    except BaseException:
        plan.rollback()
        raise
    if notify is not None:
        for codename in changed:
            notify(f"updated claim {codename!r} in roadmap/registry.yaml: touch_zones now match {node_id}")
