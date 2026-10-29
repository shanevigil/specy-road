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
from specy_road.bundled_scripts.planning_sheet_bootstrap import PROMOTE_PLACEHOLDER
from specy_road.bundled_scripts.roadmap_crud_ops import (
    append_node_to_chunk,
    run_validate_raise,
)
from specy_road.bundled_scripts.roadmap_layout import next_child_id
from specy_road.bundled_scripts.roadmap_edit_fields import EXEC_MILESTONES
from specy_road.bundled_scripts.roadmap_load import load_roadmap
from specy_road.bundled_scripts.roadmap_node_keys import new_node_key

#: Gates are human holds, not work, so an idea never becomes one.
PROMOTABLE_TYPES = ("vision", "phase", "milestone", "task")

DEFAULT_PROMOTE_TYPE = "milestone"

#: Promote kwarg default — inherit ``execution_milestone`` from the anchor.
INHERIT_EXECUTION_MILESTONE = object()


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
        f"Promoted from brainstorm idea `{idea.id}` ({idea.kind}). {PROMOTE_PLACEHOLDER}"
    )
    return "\n\n".join(parts)


def seed_planning_sheet(root: Path, node: dict, idea: Idea,
                        siblings: list[Idea] | None = None) -> Path | None:
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
    refs = _reference_lines(idea, siblings or [])
    if refs:
        parts = text.split("## References", 1)
        if len(parts) == 2:
            text = f"{parts[0]}## References\n\n" + "\n".join(refs) + f"\n{parts[1].lstrip(chr(10))}"
    sheet.write_text(text, encoding="utf-8")
    return sheet


def _reference_lines(idea: Idea, siblings: list[Idea]) -> list[str]:
    """Sources (structured ones with their quote and verification state) and the
    cluster's rejected or parked siblings, so the sheet records what was not chosen."""
    structured = {s.get("url") for s in idea.sources}
    lines = [f"- Brainstorm source: {u}" for u in idea.evidence if u not in structured]
    for s in idea.sources:
        state = s.get("verification", "unverified")
        quote = f' — "{s["quote"]}"' if s.get("quote") else ""
        lines.append(f"- Brainstorm evidence ({s.get('stance', 'for')}, {state}): {s.get('url')}{quote}")
    if idea.hypothesis:
        lines.append(f"- Hypothesis: {idea.hypothesis}")
    for a in idea.assumptions:
        lines.append(f"- Assumption: {a}")
    for sib in siblings:
        why = (sib.decision or {}).get("reason", "")
        lines.append(f"- Alternative considered: {sib.id} {sib.title} ({sib.status}" + (f": {why}" if why else "") + ")")
    return lines


def _anchor_execution_milestone(nodes: list[dict], parent_id: str | None) -> str | None:
    """The already-validated anchor's advisory execution type, when set."""
    if parent_id is None:
        return None
    anchor = next(n for n in nodes if n.get("id") == parent_id)
    em = anchor.get("execution_milestone")
    return em if em in EXEC_MILESTONES else None


def _build_node(
    nodes: list[dict],
    idea: Idea,
    *,
    parent_id: str | None,
    node_type: str,
    execution_milestone: str | None = None,
) -> dict:
    node = {
        "id": next_child_id(nodes, parent_id),
        "node_key": new_node_key(),
        "parent_id": parent_id,
        "type": node_type,
        "title": idea.title,
        "status": "Not Started",
        "execution_milestone": execution_milestone,
    }
    return {k: v for k, v in node.items() if v is not None}


def _cluster_siblings(session: BrainstormSession, idea: Idea) -> list[Idea]:
    """Rejected or parked ideas from the same converge cluster."""
    if not idea.cluster_id:
        return []
    return [i for i in session.ideas
            if i.cluster_id == idea.cluster_id and i.id != idea.id and i.status in ("rejected", "parked")]


def execution_milestone_from_promote_sets(pairs: list[str] | None) -> object:
    """Parse ``promote --set`` pairs; return :data:`INHERIT_EXECUTION_MILESTONE` when absent."""
    if not pairs:
        return INHERIT_EXECUTION_MILESTONE
    value: str | None = None
    for raw in pairs:
        if "=" not in raw:
            raise BrainstormError(
                f"promote --set expects KEY=VALUE (got {raw!r})"
            )
        key, _, raw_val = raw.partition("=")
        if key.strip() != "execution_milestone":
            raise BrainstormError(
                "promote --set only supports execution_milestone "
                f"(got {key.strip()!r})"
            )
        if raw_val.lower() in ("null", "~", ""):
            value = None
        elif raw_val not in EXEC_MILESTONES:
            raise BrainstormError(
                "execution_milestone must be one of "
                f"{sorted(EXEC_MILESTONES)} (got {raw_val!r})"
            )
        else:
            value = raw_val
    return value


def pending_ideas(session: BrainstormSession) -> list[Idea]:
    """Accepted ideas that have not been promoted yet."""
    return [
        i
        for i in session.ideas
        if i.status in PROMOTABLE_STATUSES and not i.promoted_node_key
    ]


def unverified_strong(session: BrainstormSession) -> list[Idea]:
    """Ideas about to be promoted on a ``strong`` verdict that no ``matched`` source backs."""
    return [i for i in pending_ideas(session) if i.recommendation == "strong"
            and not any(s["verification"] == "matched" for s in i.sources)]


def promote_session(
    root: Path,
    session: BrainstormSession,
    *,
    under: str | None = None,
    node_type: str = DEFAULT_PROMOTE_TYPE,
    execution_milestone: object = INHERIT_EXECUTION_MILESTONE,
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
    if execution_milestone is INHERIT_EXECUTION_MILESTONE:
        resolved_em = _anchor_execution_milestone(nodes, parent_id)
    elif execution_milestone is None:
        resolved_em = None
    elif execution_milestone not in EXEC_MILESTONES:
        raise BrainstormError(
            "execution_milestone must be one of "
            f"{sorted(EXEC_MILESTONES)} (got {execution_milestone!r})"
        )
    else:
        resolved_em = execution_milestone

    out: list[Promotion] = []
    for idea in todo:
        node = _build_node(
            nodes,
            idea,
            parent_id=parent_id,
            node_type=node_type,
            execution_milestone=resolved_em,
        )
        if dry_run:
            nodes = [*nodes, node]
            chunk = "(not written)"
        else:
            chunk_path = append_node_to_chunk(root, None, node)
            seed_planning_sheet(root, node, idea, _cluster_siblings(session, idea))
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
