"""Multi-turn chat for the PM GUI brainstorm panel.

Reuses ``review_node``'s client layer — the same four backends, the same
throughput gate, the same error redaction — but sends a conversation instead of
a single turn.

**Why searching is a text protocol rather than function calling.** The four
backends disagree about tool schemas, and one of them (``compatible``) is
whatever the user is self-hosting, where tool support is often absent. A model
that wants to search emits a ``SEARCH: <query>`` line; the server runs the
searches and appends the results as another turn. It degrades to a plain
conversation on any model, which native tool calling would not.
"""

from __future__ import annotations

import re
from typing import Any

from specy_road.bundled_scripts.brainstorm_research import (
    ResearchError,
    SearchResult,
    is_configured,
    search,
)
from specy_road.bundled_scripts.brainstorm_session import IDEA_KINDS
from specy_road.bundled_scripts.review_node import (
    ReviewError,
    _anthropic_max_completion_tokens,
    _anthropic_text,
    _azure_chat_completion_extra_params,
    _azure_deployment_for_request,
    _chat_completion_message_content,
    _make_client,
    _openai_chat_completions_create,
)

# `[ \t]` rather than `\s`: `\s` matches the newline too, so a bare `SEARCH:`
# or `IDEA:` line would reach forward and swallow the line beneath it as its
# own value.
_SEARCH_RE = re.compile(r"^[ \t]*SEARCH:[ \t]*(.+?)[ \t]*$", re.MULTILINE)
_IDEA_RE = re.compile(r"^[ \t]*IDEA:[ \t]*(.*?)[ \t]*$", re.MULTILINE)
_FIELD_RE = re.compile(
    r"^[ \t]*(WHY|KIND|EFFORT|SOURCE):[ \t]*(.+?)[ \t]*$",
    re.MULTILINE | re.IGNORECASE,
)

#: One reply should not be able to flood the board.
MAX_IDEAS_PER_TURN = 25

#: How many search rounds one user turn may trigger. Each round is a full
#: model call, so an unbounded loop is a bill as much as a hang.
MAX_SEARCH_ROUNDS = 3
MAX_QUERIES_PER_ROUND = 4

RESEARCH_INSTRUCTIONS = (
    "\n\n## Web search\n"
    "You can search the web. To do so, emit one or more lines of exactly this "
    "form and then stop, writing nothing else:\n\n"
    "SEARCH: your query here\n\n"
    "Results come back in the next turn and you continue from there. Use this "
    "for competitor moves, public complaints, technology shifts, and incoming "
    "regulation. Cite the URL you used in the idea it produced. Do not claim "
    "you searched when you did not."
)

#: The GUI has no shell. The mode prompts are written for an IDE agent and tell
#: it to run `specy-road brainstorm add-idea`, which in a chat window is just
#: text that scrolls past — the panel's idea list would never fill and triage
#: and promote would have nothing to act on. Same trade as `SEARCH:`: a text
#: protocol every backend can honour, rather than per-provider tool schemas.
IDEA_INSTRUCTIONS = (
    "\n\n## Recording ideas\n"
    "You are talking to a panel, not a terminal: shell commands you write are "
    "not run. To put an idea on the board, emit a block of exactly this form, "
    "one block per idea, alongside whatever prose you want:\n\n"
    "IDEA: short title\n"
    "WHY: one or two sentences of rationale\n"
    "KIND: one of feature, capability, risk, research, experiment\n"
    "EFFORT: one of S, M, L\n"
    "SOURCE: a URL you actually used (omit the line if none)\n\n"
    "Only WHY is optional to keep short; IDEA is required. The PM accepts or "
    "rejects each one, so err towards recording it."
)

NO_RESEARCH_NOTICE = (
    "\n\n## Web search\n"
    "Web search is not configured, so you cannot research. Brainstorm from the "
    "repository context and your own knowledge, and say plainly when a claim "
    "about the market is from memory rather than a source. Do not invent URLs. "
    "The PM can enable search in Settings → Research."
)


def _complete_anthropic(client: object, messages: list[dict], system: str) -> str:
    import os

    model = os.environ.get("SPECY_ROAD_ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
    try:
        resp = client.messages.create(  # type: ignore[union-attr]
            model=model,
            max_tokens=_anthropic_max_completion_tokens(),
            system=system,
            messages=messages,
        )
    except ReviewError:
        raise
    except Exception as e:  # noqa: BLE001 — redacted by the caller's handler
        from specy_road.bundled_scripts.review_node import _openai_safe_error_message

        raise ReviewError(_openai_safe_error_message(e)) from e
    return _anthropic_text(resp)


def complete_chat(messages: list[dict], *, system_prompt: str) -> str:
    """One model call over a whole conversation. ``messages`` is user/assistant."""
    import os

    client = _make_client()
    if type(client).__module__.startswith("anthropic"):
        return _complete_anthropic(client, messages, system_prompt)

    from openai import AzureOpenAI

    if isinstance(client, AzureOpenAI):
        model = _azure_deployment_for_request()
        extra = _azure_chat_completion_extra_params()
    else:
        model = os.environ.get("SPECY_ROAD_OPENAI_MODEL", "gpt-4o-mini")
        extra = {}
    resp = _openai_chat_completions_create(
        client,
        model=model,
        messages=[{"role": "system", "content": system_prompt}, *messages],
        **extra,
    )
    return _chat_completion_message_content(resp) or ""


def extract_queries(reply: str) -> list[str]:
    """The ``SEARCH:`` lines in a reply, deduplicated and capped."""
    seen: list[str] = []
    for match in _SEARCH_RE.findall(reply or ""):
        q = match.strip()
        if q and q not in seen:
            seen.append(q)
    return seen[:MAX_QUERIES_PER_ROUND]


def extract_ideas(reply: str) -> list[dict[str, Any]]:
    """The ``IDEA:`` blocks in a reply, in the order the model wrote them.

    A block runs from its ``IDEA:`` line to the next one, so the ``WHY``/
    ``KIND``/``EFFORT``/``SOURCE`` lines in between attach to it and prose
    around them is ignored.
    """
    text = reply or ""
    starts = [(m.start(), m.group(1).strip()) for m in _IDEA_RE.finditer(text)]
    out: list[dict[str, Any]] = []
    for i, (pos, title) in enumerate(starts):
        if not title:
            continue
        end = starts[i + 1][0] if i + 1 < len(starts) else len(text)
        fields = {
            k.upper(): v for k, v in _FIELD_RE.findall(text[pos:end])
        }
        kind = fields.get("KIND", "").strip().lower()
        source = fields.get("SOURCE", "").strip()
        out.append(
            {
                "title": title,
                "rationale": fields.get("WHY", "").strip(),
                "kind": kind if kind in IDEA_KINDS else "feature",
                "effort": fields.get("EFFORT", "").strip(),
                "evidence": [source] if source.startswith("http") else [],
            }
        )
    return out[:MAX_IDEAS_PER_TURN]


def _is_search_request(reply: str, queries: list[str]) -> bool:
    """A search turn is one whose content is only ``SEARCH:`` lines."""
    if not queries:
        return False
    remainder = _SEARCH_RE.sub("", reply or "").strip()
    return not remainder


def run_searches(
    queries: list[str],
    settings: dict[str, Any] | None,
) -> tuple[str, list[SearchResult]]:
    """Run each query; failures become text the model can read, not exceptions."""
    blocks: list[str] = []
    collected: list[SearchResult] = []
    for q in queries:
        try:
            results = search(q, settings)
        except ResearchError as e:
            blocks.append(f"### {q}\n\n_Search failed: {e}_")
            continue
        if not results:
            blocks.append(f"### {q}\n\n_No results._")
            continue
        collected.extend(results)
        blocks.append("### " + q + "\n\n" + "\n".join(r.as_line() for r in results))
    body = "\n\n".join(blocks) if blocks else "_No results._"
    return f"Search results:\n\n{body}\n\nContinue.", collected


def system_prompt_for(
    base_prompt: str,
    settings: dict[str, Any] | None,
    *,
    capture_ideas: bool = False,
) -> str:
    """The mode prompt plus whichever research capability actually exists.

    ``capture_ideas`` adds the text protocol the GUI needs; the CLI leaves it
    off because its agent records ideas by running the command itself.
    """
    tail = RESEARCH_INSTRUCTIONS if is_configured(settings) else NO_RESEARCH_NOTICE
    if capture_ideas:
        tail += IDEA_INSTRUCTIONS
    return base_prompt + tail


def chat_turn(
    messages: list[dict],
    *,
    system_prompt: str,
    research: dict[str, Any] | None = None,
    capture_ideas: bool = False,
) -> dict[str, Any]:
    """Answer one user turn, resolving any searches the model asks for.

    Returns the assistant reply plus the transcript additions the search loop
    produced, so the caller can persist a conversation that replays identically.
    When ``capture_ideas`` is set the reply's ``IDEA:`` blocks come back under
    ``ideas`` for the caller to record.
    """
    convo = list(messages)
    searched: list[str] = []
    sources: list[SearchResult] = []
    system = system_prompt_for(system_prompt, research, capture_ideas=capture_ideas)

    for _ in range(MAX_SEARCH_ROUNDS):
        reply = complete_chat(convo, system_prompt=system)
        queries = extract_queries(reply) if is_configured(research) else []
        if not _is_search_request(reply, queries):
            return {
                "reply": reply,
                "messages": convo + [{"role": "assistant", "content": reply}],
                "searched": searched,
                "sources": [s.url for s in sources],
                "ideas": extract_ideas(reply) if capture_ideas else [],
            }
        results_text, found = run_searches(queries, research)
        searched.extend(queries)
        sources.extend(found)
        convo = [
            *convo,
            {"role": "assistant", "content": reply},
            {"role": "user", "content": results_text},
        ]

    # Out of rounds: make the model answer with what it has rather than looping.
    convo.append(
        {
            "role": "user",
            "content": "Search budget reached. Answer now using what you have.",
        }
    )
    reply = complete_chat(convo, system_prompt=system)
    return {
        "reply": reply,
        "messages": convo + [{"role": "assistant", "content": reply}],
        "searched": searched,
        "sources": [s.url for s in sources],
        "ideas": extract_ideas(reply) if capture_ideas else [],
    }
