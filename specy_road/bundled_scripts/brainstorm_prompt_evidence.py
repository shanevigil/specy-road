"""The evidence prompt: sources for shortlisted ideas, quote-anchored, with a disconfirming search.

Research moves here from the first diverge round. Agent citations are right
40–80% of the time in audits, so the prompt asks for a verbatim quote, the
retrieval tool and date beside every URL; ``brainstorm verify`` then checks
the quote against the page, with the user's consent for the fetch.
"""

from __future__ import annotations

from specy_road.bundled_scripts.brainstorm_fields import STANCES
from specy_road.bundled_scripts.brainstorm_session import BrainstormSession, Idea

RESEARCH_TOOL_NOTE = (
    "Use the strongest web-research capability exposed in this session, and "
    "record which tool you used. Never claim to have used a named research "
    "product that is not exposed to you as a tool."
)


#: Past this many ideas one evidence pass turns into a skim: fewer sources each, no disconfirming search.
MAX_EVIDENCE_IDEAS = 15


def shortlist(session: BrainstormSession, ids: list[str] | None) -> list[Idea]:
    """The ids given, else the ideas the converge pass rated strong."""
    if ids:
        return [session.by_id(i) for i in ids]
    return [i for i in session.ideas if i.recommendation == "strong"
            and i.status not in ("rejected",)]


def render_evidence_prompt(session: BrainstormSession, ideas: list[Idea]) -> str:
    lines = [
        f"# Evidence: {session.topic or session.slug}",
        "",
        "The ideas below survived a first look. Your job is **evidence, not "
        "ideas**: for each one find one to three sources, and at least one "
        "search that could *disconfirm* it. Do not add ideas; do not rank.",
        "",
        RESEARCH_TOOL_NOTE,
        "",
        "## What a source must have",
        "",
        "- the URL;",
        "- a **verbatim quote** of at most 300 characters from the page that "
        "supports (or undercuts) the idea — not a paraphrase;",
        "- the claim it supports, in one line;",
        f"- the stance: {' or '.join(STANCES)};",
        "- the tool you retrieved it with (e.g. `claude WebFetch`, `codex "
        "web_search cached`, `cursor browser`) and today's date;",
        "- a source type: official-doc, regulation, paper, customer-report, "
        "news, competitor.",
        "",
        "Prefer primary sources for regulation, security, pricing and "
        "deprecations. A plausible-looking URL with no quote is worth nothing: "
        "`brainstorm verify` checks that the quote appears on the page.",
        "",
        "## Ideas",
        "",
    ]
    for i in ideas:
        lines.append(f"- **{i.id}** {i.title}" + (f" — {i.rationale}" if i.rationale else ""))
        for s in i.sources:
            lines.append(f"  - already: {s.get('url')} ({s.get('verification', 'unverified')})")
    lines += [
        "",
        "## Record each source",
        "",
        "```bash",
        f"specy-road brainstorm add-evidence B7 --slug {session.slug} \\",
        '  --url "https://..." \\',
        '  --quote "verbatim text from the page" \\',
        '  --supports "the claim this backs" --stance for \\',
        '  --tool "claude WebFetch" --source-type official-doc',
        "```",
        "",
        "`--retrieved-at` defaults to today. When you are done, hand back to "
        "the PM; they run `specy-road brainstorm verify`.",
        "",
    ]
    return "\n".join(lines) + "\n"
