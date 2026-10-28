"""Agent-facing prompt markdown for ``specy-road brainstorm``.

Three prompts over one session. The diverge prompt asks for volume and
forbids evaluation (round 1 plans and generates; later rounds regenerate
against the visible pool — :mod:`brainstorm_prompt_diverge`); the evidence
prompt asks for quote-anchored sources (:mod:`brainstorm_prompt_evidence`);
the converge prompt asks for judgement and forbids new ideas. Keeping them
apart is the whole point — an LLM asked to generate and filter in one pass
filters first, and returns five safe ideas instead of forty.

The CLI never calls a model. It assembles repo context and writes the prompt
for whichever agent is already driving the IDE, which is also the agent that
owns web search. The PM GUI runs the same prompt text against its configured
model instead.
"""

from __future__ import annotations

from pathlib import Path

from specy_road.bundled_scripts.brainstorm_fields import OVERLAP_RELATIONS
from specy_road.bundled_scripts.brainstorm_prompt_diverge import (
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
    prompt_path,
)

__all__ = [
    "render_brainstorm_prompt", "render_recommend_prompt", "render_evidence_prompt",
    "render_shard_prompt", "write_prompt",
]

#: Cap on nodes listed as "what already exists". Past this the list stops
#: being read and starts crowding out the instructions.
_MAX_EXISTING_NODES = 150

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
        if not roadmap and rel == "roadmap-context.md":
            continue
        state = "" if (root / rel).is_file() else " _(missing)_"
        lines.append(f"- **{label}:** `{rel}`{state}")
    lines.append("")
    return lines


def _existing_roadmap_lines(root: Path) -> list[str]:
    """A compact inventory of the graph, so ideas do not restate it."""
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
    for n in ordered[:_MAX_EXISTING_NODES]:
        status = n.get("rollup_status") or n.get("status") or "Not Started"
        lines.append(
            f"- `{n.get('id')}` {n.get('title', '')} — "
            f"{n.get('type', '?')} — {status}"
        )
    if len(ordered) > _MAX_EXISTING_NODES:
        rest = len(ordered) - _MAX_EXISTING_NODES
        lines.append(f"- _(+{rest} more — run `specy-road list-nodes` for the rest)_")
    lines.append("")
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
        lines += quantity_lines(count, first_round=True)
    else:
        lines = header_lines(session, count, title=f"Brainstorm, round {session.round}")
        lines += _governance_lines(root)
        lines += regeneration_lines(session, count)
        lines += quantity_lines(count, first_round=False)
    lines += recording_lines(session)
    return "\n".join(lines) + "\n"


def render_shard_prompt(root: Path, session: BrainstormSession, *, count: int,
                        shard: int, total: int) -> str:
    """One independent worker's share of round 1: its cell, nothing of the others."""
    lines = header_lines(session, count, title=f"Brainstorm shard {shard}/{total}")
    lines += _governance_lines(root, roadmap=False)
    if session.frame:
        lines += ["## The agreed frame", ""] + [f"- **{k}:** {v}" for k, v in session.frame.items()] + [""]
    lines += allocation_lines(session, count, shard=True)
    lines += shard_lines(session, shard, total)
    lines += quantity_lines(count, first_round=True)
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
    lines += _existing_roadmap_lines(root)
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
        '  --critic "feasibility: needs the billing migration first" \\',
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


def write_prompt(root: Path, session: BrainstormSession, text: str, *, suffix: str = "") -> Path:
    """Write ``work/brainstorm-<slug>[suffix]-prompt.md`` and return its path."""
    path = prompt_path(root, session.slug)
    if suffix:
        path = path.with_name(path.name.replace("-prompt.md", f"{suffix}-prompt.md"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path
