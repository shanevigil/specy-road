"""The diverge prompts: round 1 (frame + allocation), later rounds (regeneration), shards.

Round 1 sees the constitution, the frame and an allocation grid — and
deliberately **not** the roadmap node list or a research step: an inlined
inventory anchors the model to the existing solution space and early search
results anchor it to competitors (design note B3 and the anchoring evidence
behind it). Later rounds see the titles captured so far and must add only
what lies outside that pool; research is allowed from round 2. A shard is
one round-1 cell handed to an independent worker that must not see the
others' output before merge.
"""

from __future__ import annotations

from specy_road.bundled_scripts.brainstorm_lenses import (
    DEFAULT_KINDS_BY_PROFILE,
    DIRECTIONS,
    OPERATORS,
    lenses_for,
)
from specy_road.bundled_scripts.brainstorm_session import IDEA_KINDS, BrainstormSession

NO_API_NOTE = (
    "Use whatever your IDE gives you: its brainstorming or ideation slash "
    "commands and skills, sub-agents, and later its web search. specy-road "
    "calls no model and no search API from the CLI — you are the one doing "
    "this, and the tools you already have are the ones to reach for."
)


def frame_lines(session: BrainstormSession) -> list[str]:
    subject = session.topic.strip() or "the topic the PM gives you"
    lines = [
        "## Step 1 — interrogate the question before answering it",
        "",
        f"The stated topic is: **{subject}**",
        "",
        "Ask the PM these before generating. Wait for answers; a brainstorm "
        "aimed at the wrong question produces confident, useless volume.",
        "",
        "- What outcome would make this a success, stated without naming a feature?",
        "- Which metric or observable change would show it moved?",
        "- Who exactly is served, and who is deliberately not?",
        "- What has to be true for this to matter at all? Which of those is "
        "assumed rather than known?",
        "- What has already been tried here, and why did it stop?",
        "- What is being treated as fixed that is actually a choice?",
        "- What would make this topic the wrong thing to brainstorm at all?",
        "- If we did nothing in this area for a year, what would break first?",
        "",
        "Then **neutralise the frame**: rewrite every assertion the PM made "
        "(\"we obviously need X\") as a question (\"what problem does X solve, "
        "what else addresses it, what would disconfirm the need?\"). Questions "
        "draw far less agreement-seeking from you than statements do.",
        "",
        "Record the agreed frame so later rounds and other stakeholders see it:",
        "",
        "```bash",
        f"specy-road brainstorm frame --slug {session.slug} --answer "
        "\"outcome=...\" --answer \"served=...\" --answer \"not-the-question=...\"",
        "```",
        "",
    ]
    if session.frame:
        lines += ["Frame already recorded:", ""]
        lines += [f"- **{k}:** {v}" for k, v in session.frame.items()]
        lines.append("")
    return lines


def allocation_lines(session: BrainstormSession, count: int) -> list[str]:
    lenses = lenses_for(session.profile)
    lines = [
        "## Step 2 — plan the search before generating",
        "",
        f"Write an allocation grid: rows are the lenses below, columns are "
        f"the directions, and each cell you fill gets a quota; quotas sum to "
        f"at least {count}. Pick cells for *coverage* — every direction, most "
        "lenses — then attach one diversity operator to each cell. Record it:",
        "",
        "```bash",
        f"specy-road brainstorm frame --slug {session.slug} --allocation \"<grid as text>\"",
        "```",
        "",
        "**Directions:** " + "; ".join(DIRECTIONS) + ".",
        "",
        "**Lenses** (coverage scaffolding; one lens does not make an idea new):",
        "",
    ]
    lines += [f"- **{name}** — {how}" for name, how in lenses]
    lines += ["", "**Diversity operators** (these are what make the pool wide):", ""]
    lines += [f"- **{name}** — {how}" for name, how in OPERATORS]
    lines.append("")
    if session.allocation:
        lines += ["Allocation already recorded:", "", "```", session.allocation, "```", ""]
    return lines


def quantity_lines(count: int, *, first_round: bool) -> list[str]:
    lines = [
        "## Step 3 — generate, do not evaluate",
        "",
        f"Produce **at least {count} distinct ideas**. Quantity is the "
        "objective. Specifically:",
        "",
        "- Write each idea first as a two-line **concept card** in prose, for "
        "a whole cell at a time; only then record them. Filling a form per "
        "idea narrows what you think of.",
        "- Weak, obvious, and expensive ideas all belong in this pass. The PM "
        "filters later, and a bad idea next to a good one is often what makes "
        "the good one visible.",
        "- After each cell, make every idea in it **bolder and more different** "
        "from the others before moving on.",
        "- Do not rank, cluster, sequence, or estimate. Do not write "
        "\"this is the strongest option\". That is the next command's job.",
        "- Do not merge two ideas because they are similar. Record both.",
        "- Vary the altitude: some ideas should be a week of work, some a "
        "quarter, some a change of direction.",
    ]
    if first_round:
        lines += [
            "- **Do not research yet and do not read the roadmap** in this round. "
            "Both anchor you; the next round opens them.",
        ]
    lines.append("")
    return lines


def regeneration_lines(session: BrainstormSession, count: int) -> list[str]:
    lines = [
        f"## Round {session.round} — add only what is outside the pool",
        "",
        f"The pool so far has {len(session.ideas)} ideas. Read their titles:",
        "",
    ]
    lines += [f"- {i.id} {i.title}" for i in session.ideas]
    lines += [
        "",
        f"Add **at least {count} more** that are not in, and not near, that "
        "list. Mechanics that measurably widen a pool, use all three:",
        "",
        "- **Low typicality:** for each candidate, estimate the probability a "
        "typical PM would propose it; record only those under 0.2.",
        "- **Unoccupied regions:** name the regions of the solution space the "
        "pool has not touched, then put ideas in each.",
        "- **Research as a source of ideas** (now allowed): use your web search "
        "for what comparable products shipped, what users complain about in "
        "public, what changed in the underlying technology, what regulation "
        "or platform change is coming. Cite the URL with `--evidence`; the "
        "evidence pass verifies later.",
        "",
        "Same rules as before: concept cards first, no ranking, no merging, "
        "record everything.",
        "",
    ]
    return lines


def recording_lines(session: BrainstormSession, *, shard: str | None = None) -> list[str]:
    kind = DEFAULT_KINDS_BY_PROFILE.get(session.profile, "feature")
    origin = f"<harness>/<model>/<lens>/{session.round}" + (f"/{shard}" if shard else "")
    return [
        "## Record every idea",
        "",
        "One command per idea, from the repository root. Ids are allocated "
        "for you and printed.",
        "",
        "```bash",
        f"specy-road brainstorm add-idea --slug {session.slug} \\",
        '  --title "Short imperative title" \\',
        '  --rationale "Why this could matter" \\',
        f"  --kind {kind} --effort M \\",
        f'  --origin "{origin}" \\',
        '  --hypothesis "If we do this, <metric> moves because <reason>"',
        "```",
        "",
        f"`--kind` is one of {', '.join(IDEA_KINDS)}. `--origin` is "
        "harness/model/lens/round[/shard] — fill in the harness and model you "
        "are, and the lens or operator that produced the idea. `--evidence URL` "
        "repeats. Only `--title` is required.",
        "",
        "When you are done, report the count and hand back to the PM:",
        "",
        "```bash",
        f"specy-road brainstorm list --slug {session.slug}",
        "```",
        "",
        "Then stop. Do not run `promote` — accepting ideas is the PM's "
        "decision, not yours.",
        "",
    ]


def header_lines(session: BrainstormSession, count: int, *, title: str) -> list[str]:
    anchor = f"`{session.under}`" if session.under else "the roadmap root"
    return [
        f"# {title}: {session.topic or session.slug}",
        "",
        "You are running a **divergent** brainstorming session with a product "
        "manager. Your job in this session is to widen the option space, not "
        "to narrow it.",
        "",
        f"- **Session:** `{session.slug}` (round {session.round}, "
        f"profile {session.profile})",
        f"- **Anchor:** {anchor} — where accepted ideas would land",
        f"- **Target:** {count} ideas minimum",
        "",
        NO_API_NOTE,
        "",
    ]


def shard_lines(session: BrainstormSession, shard: int, total: int) -> list[str]:
    op = OPERATORS[(shard - 1) % len(OPERATORS)]
    direction = DIRECTIONS[(shard - 1) % len(DIRECTIONS)]
    return [
        f"## Shard {shard} of {total} — work alone",
        "",
        "You are one of several independent workers on this session. **Do not "
        "read the other shards' output, the session file, or the roadmap** "
        "before you finish; workers that see each other converge. Your cell:",
        "",
        f"- **Direction:** {direction}",
        f"- **Operator:** {op[0]} — {op[1]}",
        "- **Lenses:** any two of the list above that you have not been given "
        "elsewhere.",
        "",
        f"Record with `--origin <harness>/<model>/<lens>/{session.round}/s{shard}` "
        "so the merge can attribute every idea.",
        "",
    ]
