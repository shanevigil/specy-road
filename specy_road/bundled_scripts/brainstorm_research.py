"""Web search for the PM GUI brainstorm panel.

A coding agent in an IDE already has a search tool, so the CLI side of
brainstorming just tells it to use one. The GUI talks to a provider API
directly and has nothing, which is why the endpoint is configured in Settings
and called from here.

Bing's Web Search v7 shape, but the endpoint is user-supplied: anything that
answers `?q=&count=` with `{"webPages": {"value": [...]}}` works, which covers
the Azure-hosted variants and the compatible proxies people run.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests

DEFAULT_ENDPOINT = "https://api.bing.microsoft.com/v7.0/search"
_TIMEOUT_SECONDS = 20
_MAX_RESULTS_CAP = 20
_SNIPPET_MAX_CHARS = 400


class ResearchError(Exception):
    """Web search is unconfigured, disabled, or the endpoint failed."""


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str

    def as_line(self) -> str:
        return f"- {self.title} — {self.url}\n  {self.snippet}"


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


def _max_results(settings: dict[str, Any]) -> int:
    raw = str(settings.get("max_results") or "5").strip()
    try:
        n = int(raw)
    except ValueError:
        n = 5
    return max(1, min(n, _MAX_RESULTS_CAP))


def is_configured(settings: dict[str, Any] | None) -> bool:
    """True when the panel may search: enabled, with an endpoint and a key."""
    if not isinstance(settings, dict) or not _as_bool(settings.get("enabled")):
        return False
    endpoint = str(settings.get("bing_endpoint") or "").strip()
    key = str(settings.get("bing_api_key") or "").strip()
    return bool(endpoint and key)


def _require(settings: dict[str, Any] | None) -> tuple[str, str, int]:
    if not isinstance(settings, dict):
        raise ResearchError("web search is not configured")
    if not _as_bool(settings.get("enabled")):
        raise ResearchError("web search is turned off in Settings → Research")
    endpoint = str(settings.get("bing_endpoint") or "").strip()
    key = str(settings.get("bing_api_key") or "").strip()
    if not endpoint:
        raise ResearchError("web search endpoint is not set")
    if not key:
        raise ResearchError("web search API key is not set")
    return endpoint, key, _max_results(settings)


def _parse(payload: Any, limit: int) -> list[SearchResult]:
    pages = payload.get("webPages") if isinstance(payload, dict) else None
    values = pages.get("value") if isinstance(pages, dict) else None
    if not isinstance(values, list):
        return []
    out: list[SearchResult] = []
    for item in values[:limit]:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        if not url:
            continue
        snippet = str(item.get("snippet") or "").strip()
        out.append(
            SearchResult(
                title=str(item.get("name") or url).strip(),
                url=url,
                snippet=snippet[:_SNIPPET_MAX_CHARS],
            )
        )
    return out


def _safe_error(exc: BaseException) -> str:
    """Endpoint errors can echo the query string; never echo the key."""
    msg = str(exc).strip()
    return msg[:300] if msg else type(exc).__name__


def search(query: str, settings: dict[str, Any] | None) -> list[SearchResult]:
    """Run one search. Raises :class:`ResearchError` rather than returning junk."""
    endpoint, key, limit = _require(settings)
    q = query.strip()
    if not q:
        raise ResearchError("empty search query")
    try:
        resp = requests.get(
            endpoint,
            params={"q": q, "count": limit},
            headers={"Ocp-Apim-Subscription-Key": key},
            timeout=_TIMEOUT_SECONDS,
        )
    except requests.RequestException as e:
        raise ResearchError(f"search request failed: {_safe_error(e)}") from e
    if resp.status_code == 401:
        raise ResearchError("search endpoint rejected the API key (401)")
    if resp.status_code == 403:
        raise ResearchError("search endpoint refused the request (403)")
    if resp.status_code >= 400:
        raise ResearchError(f"search endpoint returned HTTP {resp.status_code}")
    try:
        payload = resp.json()
    except ValueError as e:
        raise ResearchError("search endpoint returned a non-JSON body") from e
    return _parse(payload, limit)


def test_connection(settings: dict[str, Any] | None) -> tuple[bool, str]:
    """Back the Settings "Test search" button. Never raises."""
    try:
        results = search("specy-road roadmap planning", settings)
    except ResearchError as e:
        return False, str(e)
    if not results:
        return True, "Endpoint answered, but returned no results for the test query."
    return True, f"Endpoint answered with {len(results)} result(s)."
