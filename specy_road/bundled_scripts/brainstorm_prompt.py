"""Agent-facing prompt markdown for ``specy-road brainstorm``.

Three prompts over one session, and one after it. The diverge prompt asks for volume and
forbids evaluation (round 1 plans and generates; later rounds regenerate
against the visible pool — :mod:`brainstorm_prompt_diverge`); the evidence
prompt asks for quote-anchored sources (:mod:`brainstorm_prompt_evidence`);
the converge prompt asks for judgement and forbids new ideas. Keeping them
apart is the whole point — an LLM asked to generate and filter in one pass
filters first, and returns five safe ideas instead of forty. ``promote`` then
writes an authoring prompt for the nodes it added, and seeds their sheets with
the same judgement lines (:func:`reference_lines`, :func:`constraint_lines`).

The CLI never calls a model. It assembles repo context and writes the prompt
for whichever agent is already driving the IDE, which is also the agent that
owns web search. The PM GUI runs the same prompt text against its configured
model instead.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from specy_road.bundled_scripts.brainstorm_fields import OVERLAP_RELATIONS
from specy_road.bundled_scripts.brainstorm_prompt_diverge import (
    agreed_frame_lines,
    allocation_lines,
    frame_lines,
    header_lines,
    quantity_lines,
    recording_lines,
    regeneration_lines,
    shard_lines,
)
from specy_road.bundled_scripts.brainstorm_prompt_evidence import render_evidence_prompt
from specy_road.bundled_scripts.brainstorm_session import (
    BrainstormSession,
    Idea,
    prompt_path,
    session_path,
)

if TYPE_CHECKING:  # brainstorm_promote imports this module
    from specy_road.bundled_scripts.brainstorm_promote import Promotion

__all__ = [
    "render_brainstorm_prompt", "render_recommend_prompt", "render_evidence_prompt",
    "render_shard_prompt", "render_authoring_prompt", "reference_lines", "constraint_lines",
    "write_prompt",
]

#: Cap on nodes listed as "what already exists". Past this the list stops
#: being read and starts crowding out the instructions.
_MAX_EXISTING_NODES = 150

#: Nodes the recommend prompt lists beside the phases: the ones the search
#: index ranks closest to the ideas.
_MAX_SIMILAR_NODES = 40

_GOVERNANCE_FILES: tuple[tuple[str, str], ...] = (
    ("vision.md", "Vision"),
    ("constitution/purpose.md", "Purpose"),
    ("constitution/principles.md", "Principles"),
    ("roadmap-context.md", "Current roadmap state"),
)


def _governance_lines(root: Path, *, roadmap: bool = True) -> list[str]:
    """Vision, purpose, principles — and the roadmap digest only when the round may read it."""
    lines = [
        "## Ground yourself first",
        "",
        "Read these before generating anything. Ideas that contradict the "
        "constitution waste the PM's triage time.",
        "",
    ]
    for rel, label in _GOVERNANCE_FILES:
        present = (root / rel).is_file()
        # No digest yet is normal (`specy-road digest` writes it); listing it as missing only distracts.
        if rel == "roadmap-context.md" and not (roadmap and present):
            continue
        state = "" if present else " _(missing)_"
        lines.append(f"- **{label}:** `{rel}`{state}")
    lines.append("")
    if not roadmap:
        # The managed AGENTS.md / CLAUDE.md block says to read the digest first;
        # an agent that obeys it here is anchored before it generates anything.
        lines += [
            "**Do not open `roadmap-context.md`, `roadmap.md`, anything under "
            "`roadmap/`, or `planning/` in this round**, even if AGENTS.md or "
            "CLAUDE.md says to read `roadmap-context.md` first: for this task, "
            "until you hand back to the PM, this instruction overrides that rule. "
            "The node inventory anchors ideas to what already exists.",
            "",
        ]
    return lines


def _node_line(n: dict) -> str:
    status = n.get("rollup_status") or n.get("status") or "Not Started"
    return f"- `{n.get('id')}` {n.get('title', '')} — {n.get('type', '?')} — {status}"


def _similar_node_ids(root: Path, session: BrainstormSession) -> list[str] | None:
    """Node ids the search index ranks closest to the idea titles; ``None`` when it cannot rank."""
    try:
        from specy_road.search_index import similar_node_ids

        return similar_node_ids(root, [i.title for i in session.ideas if i.title.strip()],
                                limit=_MAX_SIMILAR_NODES)
    except Exception:  # noqa: BLE001 — fall back to the full list
        return None


def _existing_roadmap_lines(root: Path, session: BrainstormSession) -> list[str]:
    """The phases plus the nodes closest to the ideas, so ideas do not restate the graph.

    Every node only when the search index cannot rank: on a large roadmap the
    full list stops being read and crowds out the instructions.
    """
    lines = ["## What already exists", ""]
    try:
        from specy_road.bundled_scripts.roadmap_load import load_roadmap

        nodes = load_roadmap(root)["nodes"]
    except Exception as e:  # noqa: BLE001 — prompt must still render
        lines += [f"_Could not load the roadmap graph: {e}_", ""]
        return lines
    if not nodes:
        lines += ["_The roadmap is empty — this is a greenfield brainstorm._", ""]
        return lines
    lines.append(
        "Do not propose work that is already on the roadmap. If an idea "
        "extends an existing node, say which one in its rationale."
    )
    lines.append("")
    ordered = sorted(nodes, key=lambda n: str(n.get("id", "")))
    ranked = _similar_node_ids(root, session)
    if ranked is None:
        lines += [_node_line(n) for n in ordered[:_MAX_EXISTING_NODES]]
        if len(ordered) > _MAX_EXISTING_NODES:
            rest = len(ordered) - _MAX_EXISTING_NODES
            lines.append(f"- _(+{rest} more — run `specy-road list-nodes` for the rest)_")
        lines.append("")
        return lines
    by_id = {str(n.get("id", "")): n for n in nodes}
    phases = [n for n in ordered if n.get("type") == "phase"]
    similar = [by_id[i] for i in ranked if i in by_id and by_id[i].get("type") != "phase"]
    lines += ["**Phases:**", ""]
    lines += [_node_line(n) for n in phases] or ["- _(none)_"]
    lines += ["", "**Nodes closest to the ideas** (ranked by the search index on the idea titles):", ""]
    lines += [_node_line(n) for n in similar] or ["- _(no node matched the idea titles)_"]
    lines += [
        "",
        f"This is {len(phases) + len(similar)} of {len(nodes)} nodes. Before you "
        "flag an idea as new, check the graph for it: `specy-road search "
        "\"<terms>\"` or `specy-road list-nodes`.",
        "",
    ]
    return lines


def render_brainstorm_prompt(
    root: Path,
    session: BrainstormSession,
    *,
    count: int,
) -> str:
    """The diverge prompt for the session's current round.

    Round 1: frame, allocation grid, volume — no roadmap inventory and no
    research (both anchor). Round 2+: the pool so far and the regeneration
    mechanics; research allowed.
    """
    if session.round <= 1:
        lines = header_lines(session, count, title="Brainstorm")
        lines += _governance_lines(root, roadmap=False)
        lines += frame_lines(session)
        lines += allocation_lines(session, count)
        lines += quantity_lines(count, first_round=True, more_rounds=session.rounds > 1)
    else:
        lines = header_lines(session, count, title=f"Brainstorm, round {session.round}")
        lines += _governance_lines(root)
        lines += agreed_frame_lines(session)
        lines += regeneration_lines(session, count)
        lines += quantity_lines(count, first_round=False)
    lines += recording_lines(session)
    return "\n".join(lines) + "\n"


def render_shard_prompt(root: Path, session: BrainstormSession, *, count: int,
                        shard: int, total: int) -> str:
    """One independent worker's share of round 1: its cell, nothing of the others."""
    lines = header_lines(session, count, title=f"Brainstorm shard {shard}/{total}")
    lines += _governance_lines(root, roadmap=False)
    lines += agreed_frame_lines(session)
    lines += allocation_lines(session, count, shard=True)
    lines += shard_lines(session, shard, total)
    lines += quantity_lines(count, first_round=True, more_rounds=session.rounds > 1)
    lines += recording_lines(session, shard=f"s{shard}")
    return "\n".join(lines) + "\n"


def _idea_inventory_lines(session: BrainstormSession) -> list[str]:
    lines = ["## The ideas to assess", ""]
    if not session.ideas:
        lines += [
            "_No ideas recorded yet — run `specy-road brainstorm start` first._",
            "",
        ]
        return lines
    for i in session.ideas:
        rec = f" — recommendation: {i.recommendation}" if i.recommendation else ""
        origin = f" [{'/'.join(i.origin.values())}]" if i.origin else ""
        lines.append(f"- **{i.id}** ({i.status}, {i.kind}){rec}{origin} — {i.title}")
        if i.rationale:
            lines.append(f"  - {i.rationale}")
        for src in i.evidence:
            lines.append(f"  - source: {src}")
        for s in i.sources:
            lines.append(f"  - evidence ({s.get('verification', 'unverified')}): {s.get('url')}")
    lines.append("")
    return lines


def render_recommend_prompt(root: Path, session: BrainstormSession) -> str:
    """The converge-mode prompt: judgement over the ideas already captured."""
    lines = [
        f"# Recommend: {session.topic or session.slug}",
        "",
        "The divergent pass is over. Switch modes: your job now is judgement, "
        "and you must not add new ideas. If you think of one, say so at the "
        "end in prose and leave the session alone.",
        "",
        f"- **Session:** `{session.slug}`",
        f"- **Ideas captured:** {len(session.ideas)}",
        "",
    ]
    lines += _governance_lines(root)
    lines += _existing_roadmap_lines(root, session)
    lines += _idea_inventory_lines(session)
    lines += [
        "## What to do",
        "",
        "1. **Cluster near-duplicates.** Name the ideas that are the same bet "
        "in different words, say which one states it best, and give each "
        "cluster an id (`C1`, `C2`, …). Singletons are clusters of one; never "
        "hide an outlier inside a cluster it does not belong to.",
        "2. **Flag overlaps with the existing roadmap** by node id, naming the "
        f"relation: {', '.join(OVERLAP_RELATIONS)}. Same-problem-same-solution "
        "duplicates committed work and should be parked with that reason.",
        "3. **Assess each idea against the constitution**, not against your "
        "own taste. An idea can be good and still be wrong for this product.",
        "4. **Play three independent critics**, one pass each, without "
        "reconciling them: *value* (who gains, how much), *feasibility* "
        "(dependencies, cost, what we would stop doing), *evidence and "
        "constitution* (what is asserted without support; which clause it "
        "strains). Record the strongest objection per cluster; keep dissent.",
        "5. **Assign a recommendation** to every idea:",
        "   - `strong` — do this; the case is clear and it fits the purpose",
        "   - `consider` — real, but needs a decision or more evidence first",
        "   - `park` — duplicate, off-purpose, or not worth the cost now",
        "   The rationale **must cite** a constitution clause, an evidence "
        "record, or an overlap — not your taste.",
        "6. **Say what is missing.** Which part of the problem got no ideas?",
        "",
        "Record each verdict, one command per idea:",
        "",
        "```bash",
        f"specy-road brainstorm revise B1 --slug {session.slug} \\",
        "  --cluster C2 --overlap M3.1:adjacent \\",
        '  --critic "feasibility: needs B4 to land first" \\',
        '  --recommendation strong --why "Principle 3; source on B1 for"',
        "```",
        "",
        "`--why` is the verdict's reasoning; `--rationale` would rewrite the "
        "idea itself. Passing only `--recommendation` and `--why` leaves the "
        "idea's triage status alone, so the PM still owns accept and reject. Finish with a short "
        "written summary: the strongest three, the clusters you merged, the "
        "sharpest dissent, and the gap you found.",
        "",
    ]
    return "\n".join(lines) + "\n"


def reference_lines(idea: Idea, siblings: list[Idea]) -> list[str]:
    """Overlaps with existing nodes, sources (structured ones with their quote and
    verification state) and the cluster's rejected or parked siblings, so the
    sheet records what already exists and what was not chosen."""
    lines = [f"- Overlaps existing node {o['node_id']} ({o['relation']})" for o in idea.overlap]
    structured = {s.get("url") for s in idea.sources}
    lines += [f"- Brainstorm source: {u}" for u in idea.evidence if u not in structured]
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


def _judgement_items(idea: Idea) -> list[str]:
    lines = [f"- {role} critic: {text}" for role, text in (idea.critic or {}).items()]
    if idea.verdict_why:
        rec = f" ({idea.recommendation})" if idea.recommendation else ""
        lines.append(f"- Verdict{rec}: {idea.verdict_why}")
    return lines


def constraint_lines(idea: Idea) -> list[str]:
    """The critics' objections and the verdict reasoning, as ``## Approach`` constraints."""
    items = _judgement_items(idea)
    return ["Constraints from the brainstorm's converge pass:", "", *items] if items else []


def _authoring_node_lines(root: Path, session: BrainstormSession,
                          promotions: list["Promotion"]) -> list[str]:
    from specy_road.bundled_scripts.roadmap_load import load_roadmap

    sheets = {n.get("id"): n.get("planning_dir") for n in load_roadmap(root)["nodes"]}
    lines = ["## The nodes to author", ""]
    for p in promotions:
        idea = session.by_id(p.idea_id)
        sheet = sheets.get(p.node_id)
        lines.append(f"### `{p.node_id}` {p.title} (from {idea.id}, {idea.kind})")
        lines.append("")
        lines.append(f"- **Sheet:** `{sheet}`" if sheet else "- **Sheet:** _(none)_")
        if idea.rationale:
            lines.append(f"- **Rationale:** {idea.rationale}")
        if idea.effort:
            lines.append(f"- **Sizing at brainstorm time:** {idea.effort}")
        lines += _judgement_items(idea)
        lines += reference_lines(idea, [])
        lines.append("")
    return lines


def render_authoring_prompt(root: Path, session: BrainstormSession,
                            promotions: list["Promotion"]) -> str:
    """After promote: draft what the seeded sheets leave open, per promoted node."""
    anchor = promotions[0].parent_id if promotions else None
    lines = [
        f"# Author promoted nodes: {session.topic or session.slug}",
        "",
        f"`specy-road brainstorm promote` added {len(promotions)} node(s) from "
        "this session. Each sheet is seeded: `## Intent` from the idea's "
        "rationale, `## Approach` with the critics' objections and the verdict "
        "as constraints, `## References` with overlaps, sources and the "
        "alternatives not chosen. Your job is the rest, drafted from the session "
        "and the repo, so each node can be picked up.",
        "",
        f"- **Session:** `work/{session_path(root, session.slug).name}`",
        f"- **Anchor:** `{anchor}`" if anchor else "- **Anchor:** _(root)_",
        "",
    ]
    lines += _governance_lines(root)
    lines += agreed_frame_lines(session)
    lines += _authoring_node_lines(root, session, promotions)
    lines += [
        "## What to do, per node",
        "",
        "1. **Intent:** rewrite it as what this slice delivers and how it fits "
        "the anchor, and delete the line `promote` added asking for that rewrite.",
        "2. **Approach:** keep the brainstorm constraints, or say in one line why "
        "one no longer applies; add the major steps and how done is verified.",
        "3. **Tasks / checklist:** replace the template item with `- [ ]` tasks.",
        "4. **Acceptance:** observable criteria, one `--set` per criterion: "
        "`specy-road edit-node <ID> --set acceptance='…' --set acceptance='…'`.",
        "5. **Touch zones:** scan the codebase for the paths the work will change "
        "or create: `specy-road edit-node <ID> --set touch_zones=a,b`.",
        "6. **References:** keep the brainstorm lines; add each `shared/` contract "
        "the node conforms to (`specy-road search \"<query>\" --kind shared`).",
        "",
        "Do not change any node's status, add or remove nodes, or edit the "
        "session file. Then run `specy-road validate`, `specy-road export` and "
        "`specy-road digest`, and hand the drafts back to the PM to approve.",
        "",
    ]
    return "\n".join(lines) + "\n"


def write_prompt(root: Path, session: BrainstormSession, text: str, *, pass_name: str) -> Path:
    """Write ``work/brainstorm-<slug>-<pass>-prompt.md`` (one file per pass) and return its path."""
    path = prompt_path(root, session.slug, pass_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path
