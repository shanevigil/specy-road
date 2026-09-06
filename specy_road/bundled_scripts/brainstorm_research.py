"""Web search for the PM GUI brainstorm panel.

A coding agent in an IDE already has a search tool, so the CLI side of
brainstorming just tells it to use one. The GUI has nothing, which is why the
back end is configured in Settings and called from here.

Which back end is a row in :mod:`brainstorm_search_providers`; this module is
only the settings, the endpoint safety check, and the call itself.
"""

from __future__ import annotations

import ipaddress
import socket
from typing import Any
from urllib.parse import urlsplit

import requests

from specy_road.bundled_scripts.brainstorm_search_providers import (
    DEFAULT_ENDPOINT,
    DEFAULT_PROVIDER,
    PROVIDERS,
    Provider,
    SearchResult,
    auth_headers,
    build_request,
    get_provider,
    parse_results,
)

__all__ = [
    "DEFAULT_ENDPOINT",
    "DEFAULT_PROVIDER",
    "PROVIDERS",
    "ResearchError",
    "SearchResult",
    "is_configured",
    "search",
    "test_connection",
    "validate_endpoint",
]

_TIMEOUT_SECONDS = 20
_MAX_RESULTS_CAP = 20

#: Both endpoint refusals are ones a self-hosted instance trips legitimately,
#: so both should say how to allow it rather than just what was rejected.
_OPT_IN_HINT = (
    " — tick 'self-hosted endpoint' in Settings → Research if that is deliberate"
)


class ResearchError(Exception):
    """Web search is unconfigured, disabled, or the endpoint failed."""


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


def _endpoint(settings: dict[str, Any], provider: Provider) -> str:
    """The configured endpoint, this provider's default, or ''.

    ``bing_endpoint`` is read as a fallback so settings written before there
    were providers keep working without a migration step.
    """
    for key in ("endpoint", "bing_endpoint"):
        value = str(settings.get(key) or "").strip()
        if value:
            return value
    return provider.default_endpoint


def _api_key(settings: dict[str, Any]) -> str:
    for key in ("api_key", "bing_api_key"):
        value = str(settings.get(key) or "").strip()
        if value:
            return value
    return ""


def is_configured(settings: dict[str, Any] | None) -> bool:
    """True when the panel may search: enabled, with whatever this provider needs."""
    if not isinstance(settings, dict) or not _as_bool(settings.get("enabled")):
        return False
    provider = get_provider(settings.get("provider"))
    if not _endpoint(settings, provider):
        return False
    return bool(_api_key(settings)) or not provider.needs_key


def _require(settings: dict[str, Any] | None) -> tuple[Provider, str, str, int]:
    if not isinstance(settings, dict):
        raise ResearchError("web search is not configured")
    if not _as_bool(settings.get("enabled")):
        raise ResearchError("web search is turned off in Settings → Research")
    provider = get_provider(settings.get("provider"))
    endpoint = _endpoint(settings, provider)
    key = _api_key(settings)
    if not endpoint:
        raise ResearchError(
            f"{provider.label} has no default endpoint — set one in "
            "Settings → Research"
        )
    if provider.needs_key and not key:
        raise ResearchError(f"{provider.label} needs an API key")
    return provider, endpoint, key, _max_results(settings)


def _is_off_host(host: str) -> bool:
    """True when ``host`` resolves to this machine or its own network."""
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return True
    for info in infos:
        try:
            addr = ipaddress.ip_address(info[4][0])
        except ValueError:
            return True
        if (
            addr.is_private
            or addr.is_loopback
            or addr.is_link_local
            or addr.is_reserved
            or addr.is_multicast
            or addr.is_unspecified
        ):
            return True
    return False


def validate_endpoint(endpoint: str, *, allow_private: bool = False) -> str:
    """The endpoint, or raise if it is not one we are willing to call.

    The GUI is reachable from any page in the browser, so an unchecked endpoint
    turns search into a probe of the host's network — cloud metadata included.
    ``allow_private`` is the deliberate exception for a self-hosted back end,
    and it also permits ``http`` because such an instance rarely has TLS.
    """
    parts = urlsplit(endpoint)
    allowed = ("http", "https") if allow_private else ("https",)
    if parts.scheme not in allowed:
        expected = "http:// or https://" if allow_private else "https://"
        raise ResearchError(
            f"search endpoint must be {expected} (got "
            f"{parts.scheme or 'no'} scheme){_OPT_IN_HINT if not allow_private else ''}"
        )
    if not parts.hostname:
        raise ResearchError("search endpoint has no host")
    if not allow_private and _is_off_host(parts.hostname):
        raise ResearchError(
            f"search endpoint host {parts.hostname!r} is not a public "
            f"address{_OPT_IN_HINT}"
        )
    return endpoint


def _safe_error(exc: BaseException) -> str:
    """Endpoint errors can echo the query string; never echo the key."""
    msg = str(exc).strip()
    return msg[:300] if msg else type(exc).__name__


def _raise_for_status(resp: requests.Response, provider: Provider) -> None:
    if resp.status_code in (401, 403):
        raise ResearchError(
            f"{provider.label} rejected the request ({resp.status_code}) — "
            "check the API key"
        )
    if 300 <= resp.status_code < 400:
        raise ResearchError(
            f"search endpoint redirected (HTTP {resp.status_code}); "
            "point the setting at the final URL"
        )
    if resp.status_code >= 400:
        raise ResearchError(f"search endpoint returned HTTP {resp.status_code}")


def search(query: str, settings: dict[str, Any] | None) -> list[SearchResult]:
    """Run one search. Raises :class:`ResearchError` rather than returning junk."""
    provider, endpoint, key, limit = _require(settings)
    allow_private = _as_bool((settings or {}).get("allow_private_endpoint"))
    validate_endpoint(endpoint, allow_private=allow_private)
    q = query.strip()
    if not q:
        raise ResearchError("empty search query")
    params, body = build_request(provider, q, limit)
    try:
        resp = requests.request(
            provider.method,
            endpoint,
            params=params,
            json=body,
            headers={"Accept": "application/json", **auth_headers(provider, key)},
            timeout=_TIMEOUT_SECONDS,
            # A redirect would carry the key to a host that never passed
            # `validate_endpoint`, which is the whole check undone.
            allow_redirects=False,
        )
    except requests.RequestException as e:
        raise ResearchError(f"search request failed: {_safe_error(e)}") from e
    _raise_for_status(resp, provider)
    try:
        payload = resp.json()
    except ValueError as e:
        raise ResearchError(
            f"{provider.label} returned a non-JSON body — is the endpoint right?"
        ) from e
    return parse_results(provider, payload, limit)


def test_connection(settings: dict[str, Any] | None) -> tuple[bool, str]:
    """Back the Settings "Test search" button. Never raises."""
    try:
        results = search("specy-road roadmap planning", settings)
    except ResearchError as e:
        return False, str(e)
    label = get_provider((settings or {}).get("provider")).label
    if not results:
        return True, f"{label} answered, but returned no results for the test query."
    return True, f"{label} answered with {len(results)} result(s)."
