"""Turn accepted brainstorm ideas into roadmap nodes.

Promoted ideas use the same add-node write as ``specy-road add-node``. The
planning sheet is seeded after that write with the converge judgement, the
anchor's sheet gains the frame, and a successful batch writes an authoring
prompt; deferred validation restores the batch if the graph is then invalid.
Which nodes to write (per idea, per cluster, or from a plan file) is decided
in ``brainstorm_promote_plan``.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from specy_road.bundled_scripts.brainstorm_prompt import (
    constraint_lines, reference_lines, render_authoring_prompt, write_prompt,
)
from specy_road.bundled_scripts.brainstorm_promote_plan import (  # pending_ideas: re-exported
    Landing, cluster_siblings, pending_ideas, select_landings,
)
from specy_road.bundled_scripts.brainstorm_session import (
    BrainstormError,
    BrainstormSession,
    Idea,
    session_path,
    write_session,
)
from specy_road.bundled_scripts.planning_artifacts import (
    normalize_planning_dir, planning_artifact_paths,
)
from specy_road.bundled_scripts.planning_sheet_bootstrap import PROMOTE_PLACEHOLDER
from specy_road.bundled_scripts.roadmap_chunk_atomic import TreeSnapshot
from specy_road.bundled_scripts.roadmap_crud_ops import (
    append_node_to_chunk, run_validate_raise,
)
from specy_road.bundled_scripts.roadmap_crud_prepare import (
    derive_codename_with_collision_suffix, next_sibling_order,
)
from specy_road.bundled_scripts.roadmap_layout import next_child_id
from specy_road.bundled_scripts.roadmap_edit_fields import CODENAME_PATTERN, EXEC_MILESTONES
from specy_road.bundled_scripts.roadmap_load import load_roadmap

#: Gates are human holds, not work, so an idea never becomes one.
PROMOTABLE_TYPES = ("vision", "phase", "milestone", "task")

DEFAULT_PROMOTE_TYPE = "milestone"

#: First N title words when deriving a promoted node's codename from its title.
PROMOTE_CODENAME_MAX_WORDS = 4

#: Promote kwarg default — inherit ``execution_milestone`` from the anchor.
INHERIT_EXECUTION_MILESTONE = object()


@dataclass(frozen=True)
class Promotion:
    """One node promote wrote, the idea that seeded it ("" for a plan node with none), and where."""

    idea_id: str
    node_id: str
    node_key: str
    title: str
    parent_id: str | None
    chunk: str
    #: Other ideas now linked to the node: cluster alternatives, or a plan node's further ideas.
    linked: tuple[str, ...] = ()


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


def _section_span(lines: list[str], heading: str) -> tuple[int, int] | None:
    """The ``## heading`` line's index and the end of its section, or None when the sheet has none."""
    start = next((i for i, ln in enumerate(lines) if ln.strip() == f"## {heading}"), None)
    if start is None:
        return None
    return start, next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))


def _replace_section(text: str, heading: str, body: str, *, append: bool = False) -> str:
    """Swap the body under a ``## heading``, leaving the rest of the sheet alone;
    with ``append``, a missing heading is added at the end instead of skipped."""
    lines, marker = text.splitlines(), f"## {heading}"
    span = _section_span(lines, heading)
    if span is None:
        return f"{text.rstrip(chr(10))}\n\n{marker}\n\n{body.strip()}\n" if append else text
    return "\n".join([*lines[:span[0]], marker, "", *body.strip().splitlines(), "", *lines[span[1]:]])


def _intent_body(idea: Idea) -> str:
    parts = [idea.rationale.strip() or idea.title.strip()]
    if idea.effort.strip():
        parts.append(f"Initial sizing at brainstorm time: {idea.effort.strip()}.")
    parts.append(f"Promoted from brainstorm idea `{idea.id}` ({idea.kind}). {PROMOTE_PLACEHOLDER}")
    return "\n\n".join(parts)


def _sheet_path(root: Path, node: dict) -> Path | None:
    pd = node.get("planning_dir")
    if not isinstance(pd, str) or not pd.strip():
        return None
    try:
        sheet = planning_artifact_paths(root, normalize_planning_dir(pd.strip()))["sheet"]
    except ValueError:
        return None
    return sheet if sheet.is_file() else None


def _prepend_to_section(text: str, heading: str, block: str) -> str:
    parts = text.split(f"## {heading}", 1)
    if len(parts) != 2:
        return text
    return f"{parts[0]}## {heading}\n\n{block}{parts[1].lstrip(chr(10))}"


def seed_planning_sheet(root: Path, node: dict, idea: Idea,
                        siblings: list[Idea] | None = None, also: list[Idea] | None = None) -> Path | None:
    """Seed ``## Intent`` from the rationale, ``## Approach`` with the critics and
    verdict as constraints, and ``## References`` with overlaps, sources, and the
    ``also`` ideas a plan node carries besides ``idea``."""
    sheet = _sheet_path(root, node)
    if sheet is None:
        return None
    text = sheet.read_text(encoding="utf-8")
    text = _replace_section(text, "Intent", _intent_body(idea))
    constraints = constraint_lines(idea)
    if constraints:
        text = _prepend_to_section(text, "Approach", "\n".join(constraints) + "\n\n")
    refs = reference_lines(idea, siblings or [])
    refs += [f"- Also promoted into this node: brainstorm idea {i.id} {i.title}" for i in also or []]
    if refs:
        text = _prepend_to_section(text, "References", "\n".join(refs) + "\n")
    sheet.write_text(text, encoding="utf-8")
    return sheet


def seed_anchor_frame(root: Path, nodes: list[dict], parent_id: str | None,
                      session: BrainstormSession) -> Path | None:  # nodes: the graph before promote
    """Write the session's recorded frame into the anchor's ``## Brainstorm frame``."""
    anchor = next((n for n in nodes if n.get("id") == parent_id), None)
    sheet = _sheet_path(root, anchor) if anchor and session.frame else None
    if sheet is None:
        return None
    lead = f"Recorded by brainstorm session `{session.slug}` before its ideas were promoted under this node."
    body = "\n".join([lead, "", *(f"- **{k}:** {v}" for k, v in session.frame.items())])
    text = _replace_section(sheet.read_text(encoding="utf-8"), "Brainstorm frame", body, append=True)
    sheet.write_text(text, encoding="utf-8")
    return sheet


def seed_decided_policies(root: Path, nodes: list[dict], anchor_id: str | None, session: BrainstormSession,
                          *, dry_run: bool = False) -> Path | None:
    """Write the session's decided ideas as ``## Decided policies`` bullets in the anchor's sheet.

    Each bullet ends with the session slug, so a re-run replaces this session's bullets
    (dropping ideas no longer decided) and leaves other sessions' alone."""
    decided = session.with_status("decided")
    anchor = next((n for n in nodes if n.get("id") == anchor_id), None)
    sheet = _sheet_path(root, anchor) if anchor else None
    if sheet is None:
        if decided:
            print(f"warning: decided idea(s) {', '.join(i.id for i in decided)} not written: "
                  f"{anchor_id or 'the roadmap root'} has no planning sheet; pass --under NODE_ID", file=sys.stderr)
        return None
    text, tag = sheet.read_text(encoding="utf-8"), f"(brainstorm `{session.slug}`"
    span = _section_span(lines := text.splitlines(), "Decided policies")
    old = [ln for ln in (lines[span[0] + 1:span[1]] if span else []) if ln.strip()]
    kept = [ln for ln in old if tag not in ln]
    if not decided and len(kept) == len(old):
        return None
    ours = [f"- **{i.title}:** {' '.join(((i.decision or {}).get('decision') or i.title).split())} {tag}, {i.id})"
            for i in decided]
    if not dry_run:
        text = _replace_section(text, "Decided policies", "\n".join([*kept, *ours]), append=True)
        sheet.write_text(text, encoding="utf-8")
    return sheet


def _promote_codename(landing: Landing, existing: set[str]) -> str | None:
    """The seeding idea's ``--codename`` on revise wins; else derive from the capped title."""
    idea = landing.ideas[0] if landing.ideas else None
    raw = (idea.codename or "").strip() if idea else ""
    if raw:
        if not CODENAME_PATTERN.match(raw):
            raise BrainstormError(f"idea {idea.id} codename {raw!r} is not valid kebab-case")
        if raw in existing:
            raise BrainstormError(f"idea {idea.id} codename {raw!r} already used on the roadmap")
        return raw
    return derive_codename_with_collision_suffix(
        landing.title, landing.node_key, existing, max_words=PROMOTE_CODENAME_MAX_WORDS,
    )


def _report_promoted_missing_fields(root: Path, promotions: list[Promotion]) -> None:
    """One stderr list of promoted nodes still without acceptance or touch zones."""
    by_id = {n["id"]: n for n in _load_nodes(root)}
    missing: list[str] = []
    for promo in promotions:
        node = by_id.get(promo.node_id)
        if not isinstance(node, dict):
            continue
        if not (isinstance(node.get("acceptance"), list) and node["acceptance"]
                and isinstance(node.get("touch_zones"), list) and node["touch_zones"]):
            missing.append(promo.node_id)
    if missing:
        print(
            "promoted node(s) still missing acceptance or touch_zones: "
            + ", ".join(missing),
            file=sys.stderr,
        )


def _anchor_execution_milestone(nodes: list[dict], parent_id: str | None) -> str | None:
    """The already-validated anchor's advisory execution type, when set."""
    if parent_id is None:
        return None
    anchor = next(n for n in nodes if n.get("id") == parent_id)
    em = anchor.get("execution_milestone")
    return em if em in EXEC_MILESTONES else None


def _promote_execution_milestone(
    nodes: list[dict], parent_id: str | None, execution_milestone: object
) -> str | None:
    if execution_milestone is INHERIT_EXECUTION_MILESTONE:
        return _anchor_execution_milestone(nodes, parent_id)
    if execution_milestone is None:
        return None
    if execution_milestone not in EXEC_MILESTONES:
        raise BrainstormError(
            "execution_milestone must be one of "
            f"{sorted(EXEC_MILESTONES)} (got {execution_milestone!r})"
        )
    return execution_milestone


def _build_node(nodes: list[dict], landing: Landing, *, parent_id: str | None,
                execution_milestone: str | None, sibling_order: int) -> dict:
    lead = landing.ideas[0] if landing.ideas else None
    node = {
        "id": next_child_id(nodes, parent_id),
        "node_key": landing.node_key,
        "parent_id": parent_id,
        "type": landing.node_type,
        "title": landing.title,
        "status": "Not Started",
        "execution_milestone": execution_milestone,
        "sibling_order": sibling_order,
        "goal": (lead.hypothesis.strip() or None) if lead else None,
        "acceptance": list(landing.acceptance) or None,
        "dependencies": list(landing.dependencies) or None,
    }
    return {k: v for k, v in node.items() if v is not None}


def unverified_strong(session: BrainstormSession) -> list[Idea]:
    """Ideas about to be promoted on a ``strong`` verdict that no ``matched`` source backs."""
    return [i for i in pending_ideas(session) if i.recommendation == "strong"
            and not any(s["verification"] == "matched" for s in i.sources)]


def _land(root: Path, session: BrainstormSession, landing: Landing, node: dict) -> str:
    """Write one node, seed its sheet, link its ideas; the chunk it landed in."""
    chunk_path = append_node_to_chunk(root, None, node, validate=False, max_words=PROMOTE_CODENAME_MAX_WORDS)
    if landing.ideas:
        lead = landing.ideas[0]
        siblings = [*landing.alternatives, *cluster_siblings(session, lead)]
        seed_planning_sheet(root, node, lead, siblings, also=landing.ideas[1:])
    for idea in landing.linked():
        idea.promoted_node_key = node["node_key"]
    write_session(root, session)
    return str(chunk_path.relative_to(root))


def _promote_landings(root: Path, session: BrainstormSession, landings: list[Landing],
                      execution_milestone: object, nodes: list[dict], dry_run: bool) -> list[Promotion]:
    """Write each landing in order; routing reads the previous node on disk."""
    out: list[Promotion] = []
    existing = {n.get("codename") for n in nodes if n.get("codename")}
    ids: dict[str, str] = {}  # landing node_key -> display id, for plan nodes under plan nodes
    simulated: dict[str | None, int] = {}  # dry run: nodes not on disk, per parent
    for landing in landings:
        parent_id = ids.get(landing.parent or "", landing.parent)
        node = _build_node(
            nodes, landing, parent_id=parent_id,
            execution_milestone=_promote_execution_milestone(nodes, parent_id, execution_milestone),
            sibling_order=next_sibling_order(root, parent_id, None) + simulated.get(parent_id, 0),
        )
        derived = _promote_codename(landing, existing)
        if derived:
            node["codename"] = derived
            existing.add(derived)
        if dry_run:
            nodes = [*nodes, node]
            simulated[parent_id] = simulated.get(parent_id, 0) + 1
            chunk = "(not written)"
        else:
            chunk = _land(root, session, landing, node)
            nodes = _load_nodes(root)
        ids[landing.node_key] = node["id"]
        out.append(Promotion(
            idea_id=landing.ideas[0].id if landing.ideas else "", node_id=node["id"],
            node_key=node["node_key"], title=landing.title, parent_id=parent_id, chunk=chunk,
            linked=tuple(i.id for i in landing.linked()[1:]),
        ))
    return out


def _assert_landings(root: Path, nodes: list[dict], landings: list[Landing]) -> None:
    """Every type promotable; every existing parent present and unlocked."""
    for landing in landings:
        if landing.node_type not in PROMOTABLE_TYPES:
            raise BrainstormError(f"type {landing.node_type!r} not one of {', '.join(PROMOTABLE_TYPES)}")
    planned = {ln.node_key for ln in landings}
    for parent in dict.fromkeys(ln.parent for ln in landings if ln.parent not in planned):
        _assert_parent(root, nodes, parent)


def promote_session(
    root: Path,
    session: BrainstormSession,
    *,
    under: str | None = None,
    node_type: str = DEFAULT_PROMOTE_TYPE,
    execution_milestone: object = INHERIT_EXECUTION_MILESTONE,
    dry_run: bool = False,
    by_cluster: bool = False,
    min_recommendation: str | None = None,
    plan: Path | None = None,
) -> list[Promotion]:
    """Promote every pending accepted idea (or ``plan``'s nodes), newest ids allocated as we go.

    An idea lands under its ``target_parent``, else ``under``, else the session
    anchor. ``min_recommendation`` leaves weaker verdicts pending; ``by_cluster``
    writes one node per cluster lead. Raises :class:`BrainstormError` before
    touching the graph when a parent or the plan is unusable. Per-node writes
    stay routing transactions; deferred validation failure restores nodes,
    sheets, and session markers.
    """
    if node_type not in PROMOTABLE_TYPES:
        raise BrainstormError(f"--type {node_type!r} not one of {', '.join(PROMOTABLE_TYPES)}")
    anchor = under if under is not None else session.under
    landings = select_landings(root, session, anchor, node_type, by_cluster=by_cluster,
                               min_recommendation=min_recommendation, plan=plan)
    decided = session.with_status("decided")
    if not landings and not decided:
        return []
    nodes = _load_nodes(root)
    _assert_landings(root, nodes, landings)
    if decided:
        _assert_parent(root, nodes, anchor)
    snap = None if dry_run or not landings else TreeSnapshot(
        (root / "roadmap", root / "planning"),
        (session_path(root, session.slug),),
    )
    out = _promote_landings(root, session, landings, execution_milestone, nodes, dry_run)
    sheet = seed_decided_policies(root, nodes, anchor, session, dry_run=dry_run)
    if sheet is not None:
        print(f"{'would write' if dry_run else 'wrote'} {len(decided)} decided idea(s) into "
              f"{sheet.relative_to(root).as_posix()} ## Decided policies", file=sys.stderr)
    if dry_run or not out:
        return out
    for parent_id in dict.fromkeys(p.parent_id for p in out):
        seed_anchor_frame(root, nodes, parent_id, session)
    try:
        run_validate_raise(root)
    except BaseException:
        assert snap is not None
        snap.restore()
        for idea in (i for ln in landings for i in ln.linked()):
            idea.promoted_node_key = None
        raise
    _report_promoted_missing_fields(root, out)
    seeded = [p for p in out if p.idea_id]  # the authoring prompt is written per idea
    if seeded:
        ppath = write_prompt(root, session, render_authoring_prompt(root, session, seeded), pass_name="authoring")
        print(f"authoring prompt: {ppath.relative_to(root)}", file=sys.stderr)
    return out
