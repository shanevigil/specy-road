"""Find a leaf whose planning sheet is still the text the toolkit wrote, whatever its acceptance.

Pickup skips such a leaf only when the node also has no ``acceptance``
(``planning_sheet_bootstrap.placeholder_sheet``): criteria give an agent
something to build from. The sheet is still unwritten, though, and a leaf that
finishes with it leaves no record of what it set out to do. So
``finish-this-task`` refuses it (``--allow-scaffold-planning`` opts out),
pickup warns about it, and ``validate`` notes the Complete leaves that already
went through.
"""

from __future__ import annotations

import sys
from pathlib import Path

from specy_road.bundled_scripts.planning_artifacts import normalize_planning_dir, resolve_planning_path
from specy_road.bundled_scripts.planning_sheet_bootstrap import (
    PROMOTE_PLACEHOLDER,
    _scaffold_bodies,
    _section_bodies,
)
from specy_road.milestone_subtree import structural_leaf_ids


def scaffold_sheet(root: Path, node: dict) -> str | None:
    """``<sheet> still has <writer>'s placeholder under ## <section>``, or ``None``.

    ``None`` too when the node has no sheet on disk; a missing sheet is
    ``validate``'s finding, not this one.
    """
    try:
        rel = normalize_planning_dir(node.get("planning_dir") or "")
        bodies = _section_bodies(resolve_planning_path(root, rel).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if PROMOTE_PLACEHOLDER in bodies.get("Intent", ""):
        return f"{rel} still has brainstorm promote's placeholder under ## Intent"
    left = [title for title, body in _scaffold_bodies().items() if body in bodies.get(title, "")]
    return f"{rel} still has scaffold-planning's placeholder under ## {left[0]}" if left else None


def scaffold_planning_or_exit(root: Path, node: dict, *, allow: bool) -> None:
    """Stop ``finish-this-task`` before any bookkeeping while the leaf's sheet is unwritten."""
    reason = None if allow else scaffold_sheet(root, node)
    if reason is None:
        return
    print(
        f"error: the planning sheet for {node['id']} was never written: {reason}.\n"
        "  Finishing would mark the node Complete with no record of what it set out to do.\n"
        "  Write its ## Intent and ## Approach and commit the sheet on this branch,\n"
        "  or pass --allow-scaffold-planning to finish anyway.",
        file=sys.stderr,
    )
    raise SystemExit(1)


def warn_scaffold_at_pickup(root: Path, node: dict) -> None:
    """One stderr line when the leaf just picked still has the scaffold sheet."""
    reason = scaffold_sheet(root, node)
    if reason is None:
        return
    print(
        f"warning: picked {node['id']}, but {reason}. Write the sheet before implementing; "
        "finish-this-task refuses it unless --allow-scaffold-planning.",
        file=sys.stderr,
    )


def notice_complete_scaffold(root: Path, nodes: list[dict], *, show_all: bool) -> None:
    """``validate``'s stdout notice counting Complete leaves still on the scaffold.

    stdout, not stderr: the work already shipped, so it is not something
    ``validate --strict`` should fail on. ``show_all`` lists each one.
    """
    leaves = structural_leaf_ids(nodes)
    found = {
        n["id"]: reason
        for n in nodes
        if n.get("id") in leaves and n.get("status") == "Complete"
        and (reason := scaffold_sheet(root, n)) is not None
    }
    if not found:
        return
    hint = "" if show_all else " (specy-road validate --all lists them)"
    print(f"notice: {len(found)} Complete leaf/leaves have a planning sheet that is still the scaffold{hint}.")
    if show_all:
        for nid, reason in found.items():
            print(f"  {nid}: {reason}")
