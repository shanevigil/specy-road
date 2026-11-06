"""The id a moved node takes: one id form per move (chosen id, lowest gap, whole outline).

Moved out of ``roadmap_move_node`` unchanged (file-limits cap) when M21.3 added
``--rewrite-refs`` there; ``_apply_move`` is the only caller.
"""

from __future__ import annotations

from specy_road.bundled_scripts.roadmap_outline_renumber import (
    check_chosen_child_id,
    lowest_free_child_id,
    next_free_child_id,
    subtree_ids,
)


def _refuse_id_form_combinations(forms: dict[str, bool]) -> None:
    """One rule: a move picks at most one id form (chosen id, lowest gap, whole outline)."""
    given = [name for name, on in forms.items() if on]
    if len(given) > 1:
        raise ValueError(
            f"{' and '.join(given)} are mutually exclusive: pick at most one id form"
        )


def _moved_node_id(
    nodes: list[dict],
    node_key: str,
    old_id: str,
    parent_id: str | None,
    new_id: str | None,
    fill_gaps: bool,
) -> str:
    """The id the moved node takes under a subtree-only move."""
    if new_id is None and not fill_gaps:
        return next_free_child_id(nodes, parent_id, exclude_key=node_key)
    ignore = subtree_ids(nodes, old_id)
    if fill_gaps:
        return lowest_free_child_id(nodes, parent_id, ignore_ids=ignore)
    check_chosen_child_id(nodes, parent_id, new_id, ignore_ids=ignore)
    return new_id
