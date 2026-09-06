"""Agent-facing prompt markdown for ``specy-road brainstorm``.

Two prompts, one per mode. The diverge prompt asks for volume and forbids
evaluation; the converge prompt asks for judgement and forbids new ideas.
Keeping them apart is the whole point — an LLM asked to generate and filter in
one pass filters first, and returns five safe ideas instead of forty.

The CLI never calls a model. It assembles repo context and writes the prompt
for whichever agent is already driving the IDE, which is also the agent that
owns web search. The PM GUI runs the same prompt text against its configured
model instead.
"""

from __future__ import annotations

from pathlib import Path

from specy_road.bundled_scripts.brainstorm_session import (
    BrainstormSession,
    prompt_path,
)

#: Cap on nodes listed as "what already exists". Past this the list stops
#: being read and starts crowding out the instructions.
_MAX_EXISTING_NODES = 150

_GOVERNANCE_FILES: tuple[tuple[str, str], ...] = (
    ("vision.md", "Vision"),
    ("constitution/purpose.md", "Purpose"),
    ("constitution/principles.md", "Principles"),
    ("roadmap-context.md", "Current roadmap state"),
)

_TECHNIQUES: tuple[tuple[str, str], ...] = (
    (
        "SCAMPER",
        "Substitute, Combine, Adapt, Modify, Put to another use, Eliminate, "
        "Reverse — run each verb against the product's existing surfaces.",
    ),
    (
        "Analogous domains",
        "How has a different industry solved the shape of this problem? "
        "Logistics, games, banking, healthcare. Port the mechanism, not the "
        "feature.",
    ),
    (
        "Inversion",
        "What would make this dramatically worse for the user? Invert each "
        "answer into something to build.",
    ),
    (
        "Pre-mortem",
        "It is a year from now and this area failed. Write the causes, then "
        "propose the work that would have prevented each one.",
    ),
    (
        "Constraint removal",
        "Drop the hardest current constraint (budget, latency, headcount, a "
        "vendor) and say what becomes possible.",
    ),
    (
        "10x / 0.1x",
        "What would this look like with ten times the users, and what would "
        "the smallest useful version be that ships in a week?",
    ),
)


def _governance_lines(root: Path) -> list[str]:
    lines = [
        "## Ground yourself first",
        "",
        "Read these before generating anything. Ideas that contradict the "
        "constitution waste the PM's triage time.",
        "",
    ]
    for rel, label in _GOVERNANCE_FILES:
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


def _socratic_lines(topic: str) -> list[str]:
    subject = topic.strip() or "the topic the PM gives you"
    return [
        "## Step 1 — interrogate the question before answering it",
        "",
        f"The stated topic is: **{subject}**",
        "",
        "Ask the PM these before generating. Wait for answers; a brainstorm "
        "aimed at the wrong question produces confident, useless volume.",
        "",
        "- What outcome would make this a success, stated without naming a feature?",
        "- Who exactly is served, and who is deliberately not?",
        "- What has to be true for this to matter at all? Which of those is "
        "assumed rather than known?",
        "- What has already been tried here, and why did it stop?",
        "- What is being treated as fixed that is actually a choice?",
        "- If we did nothing in this area for a year, what would break first?",
        "",
        "Summarise what you heard in two or three sentences and get agreement "
        "before Step 2.",
        "",
    ]


def _quantity_lines(count: int) -> list[str]:
    return [
        "## Step 2 — generate, do not evaluate",
        "",
        f"Produce **at least {count} distinct ideas**. Quantity is the "
        "objective. Specifically:",
        "",
        "- Weak, obvious, and expensive ideas all belong in this pass. The PM "
        "filters later, and a bad idea next to a good one is often what makes "
        "the good one visible.",
        "- Do not stop at the first coherent set. The last third of a list is "
        "where the non-obvious ideas live, so push past the point where it "
        "feels finished.",
        "- Do not rank, cluster, sequence, or estimate. Do not write "
        "\"this is the strongest option\". That is the next command's job.",
        "- Do not merge two ideas because they are similar. Record both.",
        "- Vary the altitude: some ideas should be a week of work, some a "
        "quarter, some a change of direction.",
        "",
    ]


def _technique_lines() -> list[str]:
    lines = [
        "Work through these lenses in order rather than free-associating. "
        "Each one should yield several ideas; note which lens produced an "
        "idea in its rationale when it is not obvious.",
        "",
    ]
    for name, how in _TECHNIQUES:
        lines.append(f"- **{name}** — {how}")
    lines.append("")
    return lines


def _research_lines() -> list[str]:
    return [
        "## Step 3 — research, with your own tools",
        "",
        "Use your web search tool. Do not brainstorm only from what you "
        "already know; the point of researching is to import ideas that are "
        "not in the room.",
        "",
        "Use whatever your IDE gives you here: its brainstorming or ideation "
        "slash commands and skills, if it has any, alongside your own search. "
        "specy-road calls no model and no search API from the CLI — you are "
        "the one doing this, and the tools you already have are the ones to "
        "reach for.",
        "",
        "- What have comparable products shipped in this area recently?",
        "- What are users complaining about, in public, for this class of "
        "product?",
        "- What has changed in the underlying technology that makes something "
        "newly cheap or newly possible?",
        "- What regulation, standard, or platform change is coming that "
        "forces work regardless of preference?",
        "",
        "Record the URL you drew from in `--evidence` on the idea it "
        "produced. An idea with a source survives triage; an unsourced claim "
        "about a competitor does not.",
        "",
    ]


def _recording_lines(slug: str) -> list[str]:
    return [
        "## Step 4 — record every idea",
        "",
        "One command per idea, from the repository root. Ids are allocated "
        "for you and printed.",
        "",
        "```bash",
        f"specy-road brainstorm add-idea --slug {slug} \\",
        '  --title "Short imperative title" \\',
        '  --rationale "Why this could matter, and which lens produced it" \\',
        "  --kind feature \\",
        "  --effort M \\",
        '  --evidence "https://source-you-found"',
        "```",
        "",
        "`--kind` is one of `feature`, `capability`, `risk`, `research`, "
        "`experiment`. `--effort` is a free-form t-shirt size. `--evidence` "
        "repeats for multiple sources. Only `--title` is required.",
        "",
        "When you are done, report the count and hand back to the PM:",
        "",
        "```bash",
        f"specy-road brainstorm list --slug {slug}",
        "```",
        "",
        "Then stop. Do not run `promote` — accepting ideas is the PM's "
        "decision, not yours.",
        "",
    ]


def render_brainstorm_prompt(
    root: Path,
    session: BrainstormSession,
    *,
    count: int,
) -> str:
    """The diverge-mode prompt: Socratic opening, then volume."""
    anchor = f"`{session.under}`" if session.under else "the roadmap root"
    lines = [
        f"# Brainstorm: {session.topic or session.slug}",
        "",
        "You are running a **divergent** brainstorming session with a product "
        "manager. Your job in this session is to widen the option space, not "
        "to narrow it.",
        "",
        f"- **Session:** `{session.slug}`",
        f"- **Anchor:** {anchor} — where accepted ideas would land",
        f"- **Target:** {count} ideas minimum",
        "",
    ]
    lines += _governance_lines(root)
    lines += _existing_roadmap_lines(root)
    lines += _socratic_lines(session.topic)
    lines += _quantity_lines(count)
    lines += _technique_lines()
    lines += _research_lines()
    lines += _recording_lines(session.slug)
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
        lines.append(f"- **{i.id}** ({i.status}, {i.kind}){rec} — {i.title}")
        if i.rationale:
            lines.append(f"  - {i.rationale}")
        for src in i.evidence:
            lines.append(f"  - source: {src}")
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
        "in different words, and say which one states it best.",
        "2. **Flag overlaps with the existing roadmap** by node id. An idea "
        "that duplicates committed work should be parked with that reason.",
        "3. **Assess each idea against the constitution**, not against your "
        "own taste. An idea can be good and still be wrong for this product.",
        "4. **Assign a recommendation** to every idea:",
        "   - `strong` — do this; the case is clear and it fits the purpose",
        "   - `consider` — real, but needs a decision or more evidence first",
        "   - `park` — duplicate, off-purpose, or not worth the cost now",
        "5. **Say what is missing.** Which part of the problem got no ideas?",
        "",
        "Record each verdict, one command per idea:",
        "",
        "```bash",
        f"specy-road brainstorm revise B1 --slug {session.slug} \\",
        '  --recommendation strong --rationale "One line on why"',
        "```",
        "",
        "Passing only `--recommendation` leaves the idea's triage status "
        "alone, so the PM still owns accept and reject. Finish with a short "
        "written summary: the strongest three, the clusters you merged, and "
        "the gap you found.",
        "",
    ]
    return "\n".join(lines) + "\n"


def write_prompt(root: Path, session: BrainstormSession, text: str) -> Path:
    """Write ``work/brainstorm-<slug>-prompt.md`` and return its path."""
    path = prompt_path(root, session.slug)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path
