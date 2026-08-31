"""Work a roadmap mutation does *before* it stages anything.

Split out of :mod:`roadmap_crud_ops` to stay inside the repo's per-file line
cap; the ``roadmap_crud_*`` modules follow the same pattern.

Both helpers exist for the same reason: repairs must not happen inside a
mutation's transaction. The self-heal pass rewrites chunks and renames planning
sheets, and a new task needs a codename that the heal would otherwise derive —
from inside validation, where those writes escape the atomic plan's snapshot and
survive its rollback.
"""

from __future__ import annotations

import sys
from pathlib import Path

from roadmap_load import load_roadmap


def heal_before_mutation(root: Path) -> None:
    """Run validate's self-heal pass before a mutation reads the graph.

    Idempotent and silent when there is nothing to fix, so legacy repos keep
    self-repairing without smuggling untracked writes into a transaction.
    """
    from validate_self_heal import auto_heal_roadmap

    try:
        auto_heal_roadmap(root)
    except (KeyError, OSError, SystemExit, TypeError, ValueError):
        # A graph too broken to heal is strict validation's problem to report,
        # with the real error rather than a heal traceback.
        return


def derive_codename_with_collision_suffix(
    title: str, node_key: str, existing: set[str]
) -> str | None:
    """
    Derive a kebab-case codename from ``title``; if a collision exists,
    append ``-<last 4 hex of node_key>`` to disambiguate (F-006).

    Returns ``None`` when no valid codename can be derived from the title
    (e.g. empty or all-punctuation titles); callers may leave the node
    unnamed so ``validate`` can re-visit it later.
    """
    from roadmap_edit_fields import title_to_codename

    slug = title_to_codename(title)
    if not slug:
        return None
    if slug not in existing:
        return slug
    tail = (node_key or "").replace("-", "")[-4:] or "x"
    cand = f"{slug}-{tail}"
    # Very defensive: extend the tail if still colliding.
    if cand in existing and node_key:
        cand = f"{slug}-{(node_key or '').replace('-', '')[-6:] or 'xx'}"
    return cand


def ensure_codename_for_new_node(root: Path, node: dict) -> None:
    """F-006: give a new task a codename from its title, before it is written.

    Downstream pickup and registry logic need one. Deriving it here keeps every
    add path (CLI and PM GUI) producing complete nodes.
    """
    if node.get("type") != "task" or node.get("codename"):
        return
    existing = {
        n.get("codename") for n in load_roadmap(root)["nodes"] if n.get("codename")
    }
    derived = derive_codename_with_collision_suffix(
        str(node.get("title") or ""), str(node.get("node_key") or ""), existing
    )
    if not derived:
        return
    node["codename"] = derived
    print(
        f"[heal] node {node.get('id', '?')}: codename auto-derived as "
        f"{derived!r} from title (see validate for collision rules)",
        file=sys.stderr,
    )
