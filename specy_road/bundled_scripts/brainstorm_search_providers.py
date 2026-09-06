"""The web search back ends the brainstorm panel can talk to.

Every one of these answers a query with a list of ``{title, url, snippet}``;
they disagree only about where the key goes, what the query field is called,
and where the list sits in the response. So they are a table rather than seven
classes — adding one is a row, and a row is hard to get subtly wrong.

Self-hosted instances (SearXNG especially) usually live on a private address,
which the endpoint check refuses by default; ``allow_private`` in the research
settings is the opt-in for that.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

_SNIPPET_MAX_CHARS = 400


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str

    def as_line(self) -> str:
        return f"- {self.title} — {self.url}\n  {self.snippet}"


@dataclass(frozen=True)
class Provider:
    """One search back end, described rather than implemented."""

    key: str
    label: str
    #: Blank when the user must supply it — self-hosted back ends have no default.
    default_endpoint: str
    method: str
    #: Blank when the back end takes no credential.
    auth_header: str
    #: ``{key}`` is substituted; some back ends want a ``Bearer`` prefix.
    auth_format: str
    query_field: str
    #: Blank when the back end has no result-count parameter; we slice instead.
    limit_field: str
    results_path: tuple[str, ...]
    title_key: str
    url_key: str
    snippet_key: str
    needs_key: bool = True
    #: Sent alongside the query on every request.
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def posts_json(self) -> bool:
        return self.method == "POST"


PROVIDERS: dict[str, Provider] = {
    "bing": Provider(
        key="bing",
        label="Bing / Azure Web Search",
        default_endpoint="https://api.bing.microsoft.com/v7.0/search",
        method="GET",
        auth_header="Ocp-Apim-Subscription-Key",
        auth_format="{key}",
        query_field="q",
        limit_field="count",
        results_path=("webPages", "value"),
        title_key="name",
        url_key="url",
        snippet_key="snippet",
    ),
    "tavily": Provider(
        key="tavily",
        label="Tavily",
        default_endpoint="https://api.tavily.com/search",
        method="POST",
        auth_header="Authorization",
        auth_format="Bearer {key}",
        query_field="query",
        limit_field="max_results",
        results_path=("results",),
        title_key="title",
        url_key="url",
        snippet_key="content",
    ),
    "searxng": Provider(
        key="searxng",
        label="SearXNG (self-hosted)",
        default_endpoint="",
        method="GET",
        auth_header="",
        auth_format="",
        query_field="q",
        limit_field="",
        results_path=("results",),
        title_key="title",
        url_key="url",
        snippet_key="content",
        needs_key=False,
        extra={"format": "json"},
    ),
    "brave": Provider(
        key="brave",
        label="Brave Search",
        default_endpoint="https://api.search.brave.com/res/v1/web/search",
        method="GET",
        auth_header="X-Subscription-Token",
        auth_format="{key}",
        query_field="q",
        limit_field="count",
        results_path=("web", "results"),
        title_key="title",
        url_key="url",
        snippet_key="description",
    ),
    "serper": Provider(
        key="serper",
        label="Serper (Google)",
        default_endpoint="https://google.serper.dev/search",
        method="POST",
        auth_header="X-API-KEY",
        auth_format="{key}",
        query_field="q",
        limit_field="num",
        results_path=("organic",),
        title_key="title",
        url_key="link",
        snippet_key="snippet",
    ),
    "exa": Provider(
        key="exa",
        label="Exa",
        default_endpoint="https://api.exa.ai/search",
        method="POST",
        auth_header="x-api-key",
        auth_format="{key}",
        query_field="query",
        limit_field="numResults",
        results_path=("results",),
        title_key="title",
        url_key="url",
        snippet_key="text",
    ),
    "firecrawl": Provider(
        key="firecrawl",
        label="Firecrawl",
        default_endpoint="https://api.firecrawl.dev/v1/search",
        method="POST",
        auth_header="Authorization",
        auth_format="Bearer {key}",
        query_field="query",
        limit_field="limit",
        results_path=("data",),
        title_key="title",
        url_key="url",
        snippet_key="description",
    ),
}

DEFAULT_PROVIDER = "bing"

#: Kept so settings written before providers existed still name something real.
DEFAULT_ENDPOINT = PROVIDERS[DEFAULT_PROVIDER].default_endpoint


def get_provider(name: str | None) -> Provider:
    """The named provider, falling back to the default rather than raising."""
    return PROVIDERS.get(str(name or "").strip().lower(), PROVIDERS[DEFAULT_PROVIDER])


def auth_headers(provider: Provider, key: str) -> dict[str, str]:
    if not provider.auth_header or not key:
        return {}
    return {provider.auth_header: provider.auth_format.format(key=key)}


def build_request(
    provider: Provider, query: str, limit: int
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """``(params, json_body)`` for this provider — exactly one of them is set."""
    payload: dict[str, Any] = {provider.query_field: query, **provider.extra}
    if provider.limit_field:
        payload[provider.limit_field] = limit
    return (None, payload) if provider.posts_json else (payload, None)


def _dig(payload: Any, path: tuple[str, ...]) -> list[Any]:
    """The result list at ``path``, or empty when the shape is not what we expect."""
    cur = payload
    for step in path:
        if not isinstance(cur, dict):
            return []
        cur = cur.get(step)
    return cur if isinstance(cur, list) else []


def parse_results(provider: Provider, payload: Any, limit: int) -> list[SearchResult]:
    """Read this provider's response shape into results, skipping unusable rows."""
    out: list[SearchResult] = []
    for item in _dig(payload, provider.results_path)[:limit]:
        if not isinstance(item, dict):
            continue
        url = str(item.get(provider.url_key) or "").strip()
        if not url:
            continue
        snippet = str(item.get(provider.snippet_key) or "").strip()
        out.append(
            SearchResult(
                title=str(item.get(provider.title_key) or url).strip(),
                url=url,
                snippet=snippet[:_SNIPPET_MAX_CHARS],
            )
        )
    return out
