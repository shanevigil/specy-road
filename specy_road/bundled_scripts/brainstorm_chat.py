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

_SEARCH_RE = re.compile(r"^\s*SEARCH:\s*(.+?)\s*$", re.MULTILINE)

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


def system_prompt_for(base_prompt: str, settings: dict[str, Any] | None) -> str:
    """The mode prompt plus whichever research capability actually exists."""
    tail = RESEARCH_INSTRUCTIONS if is_configured(settings) else NO_RESEARCH_NOTICE
    return base_prompt + tail


def chat_turn(
    messages: list[dict],
    *,
    system_prompt: str,
    research: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Answer one user turn, resolving any searches the model asks for.

    Returns the assistant reply plus the transcript additions the search loop
    produced, so the caller can persist a conversation that replays identically.
    """
    convo = list(messages)
    searched: list[str] = []
    sources: list[SearchResult] = []
    system = system_prompt_for(system_prompt, research)

    for _ in range(MAX_SEARCH_ROUNDS):
        reply = complete_chat(convo, system_prompt=system)
        queries = extract_queries(reply) if is_configured(research) else []
        if not _is_search_request(reply, queries):
            return {
                "reply": reply,
                "messages": convo + [{"role": "assistant", "content": reply}],
                "searched": searched,
                "sources": [s.url for s in sources],
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
    }
