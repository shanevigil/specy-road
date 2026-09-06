"""Turn accepted brainstorm ideas into roadmap nodes.

The converge step. Everything here routes through the same mutation path as
``specy-road add-node`` — ``append_node_to_chunk`` stages the chunk, the
manifest and the planning sheet in one transaction — so a promoted idea is
indistinguishable from a hand-authored node once it lands.

The sheet is seeded afterwards rather than inside that transaction: the
scaffold is already valid, and enriching it is a plain markdown edit that can
fail without leaving the graph inconsistent.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from specy_road.bundled_scripts.brainstorm_session import (
    BrainstormError,
    BrainstormSession,
    Idea,
    PROMOTABLE_STATUSES,
    write_session,
)
from specy_road.bundled_scripts.planning_artifacts import (
    normalize_planning_dir,
    planning_artifact_paths,
)
from specy_road.bundled_scripts.roadmap_crud_ops import (
    append_node_to_chunk,
    run_validate_raise,
)
from specy_road.bundled_scripts.roadmap_layout import next_child_id
from specy_road.bundled_scripts.roadmap_load import load_roadmap
from specy_road.bundled_scripts.roadmap_node_keys import new_node_key

#: Gates are human holds, not work, so an idea never becomes one.
PROMOTABLE_TYPES = ("vision", "phase", "milestone", "task")

DEFAULT_PROMOTE_TYPE = "milestone"


@dataclass(frozen=True)
class Promotion:
    """One idea's landing: which node it became, and where."""

    idea_id: str
    node_id: str
    node_key: str
    title: str
    parent_id: str | None
    chunk: str


def _load_nodes(root: Path) -> list[dict]:
    return load_roadmap(root)["nodes"]


def _assert_parent(root: Path, nodes: list[dict], parent_id: str | None) -> None:
    """Parent must exist and must not sit in a locked milestone subtree."""
    if parent_id is None:
        return
    if not any(n.get("id") == parent_id for n in nodes):
        raise BrainstormError(f"anchor node {parent_id!r} is not in the roadmap")
    from specy_road.milestone_lock import assert_pm_nodes_not_milestone_locked

    try:
        assert_pm_nodes_not_milestone_locked(nodes, parent_id)
    except ValueError as e:
        raise BrainstormError(str(e)) from e


def _replace_section(text: str, heading: str, body: str) -> str:
    """Swap the body under a ``## heading``, leaving the rest of the sheet alone."""
    lines = text.splitlines()
    marker = f"## {heading}"
    try:
        start = next(i for i, ln in enumerate(lines) if ln.strip() == marker)
    except StopIteration:
        return text
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if lines[i].startswith("## "):
            end = i
            break
    replacement = [marker, "", *body.strip().splitlines(), ""]
    return "\n".join([*lines[:start], *replacement, *lines[end:]])


def _intent_body(idea: Idea) -> str:
    parts = [idea.rationale.strip() or idea.title.strip()]
    if idea.effort.strip():
        parts.append(f"Initial sizing at brainstorm time: {idea.effort.strip()}.")
    parts.append(
        f"Promoted from brainstorm idea `{idea.id}` ({idea.kind}). "
        "Rewrite this section once the slice is properly scoped."
    )
    return "\n\n".join(parts)


def seed_planning_sheet(root: Path, node: dict, idea: Idea) -> Path | None:
    """Write the idea's rationale into the scaffolded sheet's ``## Intent``."""
    pd = node.get("planning_dir")
    if not isinstance(pd, str) or not pd.strip():
        return None
    try:
        paths = planning_artifact_paths(root, normalize_planning_dir(pd.strip()))
    except ValueError:
        return None
    sheet = paths["sheet"]
    if not sheet.is_file():
        return None
    text = sheet.read_text(encoding="utf-8")
    text = _replace_section(text, "Intent", _intent_body(idea))
    if idea.evidence:
        sources = "\n".join(f"- Brainstorm source: {u}" for u in idea.evidence)
        refs = text.split("## References", 1)
        if len(refs) == 2:
            text = f"{refs[0]}## References\n\n{sources}\n{refs[1].lstrip(chr(10))}"
    sheet.write_text(text, encoding="utf-8")
    return sheet


def _build_node(
    nodes: list[dict],
    idea: Idea,
    *,
    parent_id: str | None,
    node_type: str,
) -> dict:
    node = {
        "id": next_child_id(nodes, parent_id),
        "node_key": new_node_key(),
        "parent_id": parent_id,
        "type": node_type,
        "title": idea.title,
        "status": "Not Started",
    }
    return {k: v for k, v in node.items() if v is not None}


def pending_ideas(session: BrainstormSession) -> list[Idea]:
    """Accepted ideas that have not been promoted yet."""
    return [
        i
        for i in session.ideas
        if i.status in PROMOTABLE_STATUSES and not i.promoted_node_key
    ]


def promote_session(
    root: Path,
    session: BrainstormSession,
    *,
    under: str | None = None,
    node_type: str = DEFAULT_PROMOTE_TYPE,
    dry_run: bool = False,
) -> list[Promotion]:
    """Promote every pending accepted idea, newest ids allocated as we go.

    Raises :class:`BrainstormError` before touching the graph when the anchor is
    unusable, so a bad ``--under`` promotes nothing.

    Each node is its own transaction — the router's choice of chunk depends on
    what the previous write left on disk, so the batch cannot be one. The
    session is therefore saved after every node rather than by the caller at the
    end: if idea three fails, the two already on the graph are recorded as
    promoted, and re-running promotes the rest instead of duplicating them.
    """
    if node_type not in PROMOTABLE_TYPES:
        raise BrainstormError(
            f"--type {node_type!r} not one of {', '.join(PROMOTABLE_TYPES)}"
        )
    todo = pending_ideas(session)
    if not todo:
        return []
    parent_id = under if under is not None else session.under
    nodes = _load_nodes(root)
    _assert_parent(root, nodes, parent_id)

    out: list[Promotion] = []
    for idea in todo:
        node = _build_node(nodes, idea, parent_id=parent_id, node_type=node_type)
        if dry_run:
            nodes = [*nodes, node]
            chunk = "(not written)"
        else:
            chunk_path = append_node_to_chunk(root, None, node)
            seed_planning_sheet(root, node, idea)
            idea.promoted_node_key = node["node_key"]
            write_session(root, session)
            chunk = str(chunk_path.relative_to(root))
            nodes = _load_nodes(root)
        out.append(
            Promotion(
                idea_id=idea.id,
                node_id=node["id"],
                node_key=node["node_key"],
                title=idea.title,
                parent_id=parent_id,
                chunk=chunk,
            )
        )
    if not dry_run and out:
        run_validate_raise(root)
    return out
