"""Every search back end the panel offers, one row of the table at a time.

The providers are a table, so the risk is not that the code is wrong but that
a row is: the wrong header name, the wrong query field, the wrong path into
the response. Each of these pins one row against a recorded response shape.
"""

from __future__ import annotations

from typing import Any

import pytest

from specy_road.bundled_scripts.brainstorm_research import (
    ResearchError,
    is_configured,
    search,
    validate_endpoint,
)
from specy_road.bundled_scripts.brainstorm_search_providers import (
    PROVIDERS,
    auth_headers,
    build_request,
    get_provider,
    parse_results,
)

#: One recorded response body per provider, trimmed to the shape we read.
RESPONSES: dict[str, Any] = {
    "bing": {
        "webPages": {
            "value": [
                {"name": "T", "url": "https://e/1", "snippet": "S"},
                {"name": "T2", "url": "https://e/2", "snippet": "S2"},
            ]
        }
    },
    "tavily": {
        "results": [
            {"title": "T", "url": "https://e/1", "content": "S"},
            {"title": "T2", "url": "https://e/2", "content": "S2"},
        ]
    },
    "searxng": {
        "results": [
            {"title": "T", "url": "https://e/1", "content": "S"},
            {"title": "T2", "url": "https://e/2", "content": "S2"},
        ]
    },
    "brave": {
        "web": {
            "results": [
                {"title": "T", "url": "https://e/1", "description": "S"},
                {"title": "T2", "url": "https://e/2", "description": "S2"},
            ]
        }
    },
    "serper": {
        "organic": [
            {"title": "T", "link": "https://e/1", "snippet": "S"},
            {"title": "T2", "link": "https://e/2", "snippet": "S2"},
        ]
    },
    "exa": {
        "results": [
            {"title": "T", "url": "https://e/1", "text": "S"},
            {"title": "T2", "url": "https://e/2", "text": "S2"},
        ]
    },
    "firecrawl": {
        "data": [
            {"title": "T", "url": "https://e/1", "description": "S"},
            {"title": "T2", "url": "https://e/2", "description": "S2"},
        ]
    },
}


def test_every_provider_has_a_recorded_response() -> None:
    """A new row in the table needs a new row here, or it is untested."""
    assert set(RESPONSES) == set(PROVIDERS)


@pytest.mark.parametrize("name", sorted(PROVIDERS))
def test_each_provider_reads_its_own_response_shape(name: str) -> None:
    results = parse_results(PROVIDERS[name], RESPONSES[name], 5)

    assert [r.url for r in results] == ["https://e/1", "https://e/2"]
    assert [r.title for r in results] == ["T", "T2"]
    assert [r.snippet for r in results] == ["S", "S2"]


@pytest.mark.parametrize("name", sorted(PROVIDERS))
def test_each_provider_respects_the_result_cap(name: str) -> None:
    assert len(parse_results(PROVIDERS[name], RESPONSES[name], 1)) == 1


@pytest.mark.parametrize("name", sorted(PROVIDERS))
def test_a_junk_response_yields_nothing_rather_than_raising(name: str) -> None:
    """A wrong endpoint answers 200 with something else; that is not a crash."""
    for junk in ({}, {"unexpected": 1}, [], "text", None):
        assert parse_results(PROVIDERS[name], junk, 5) == []


@pytest.mark.parametrize(
    "name,header",
    [
        ("bing", "Ocp-Apim-Subscription-Key"),
        ("tavily", "Authorization"),
        ("brave", "X-Subscription-Token"),
        ("serper", "X-API-KEY"),
        ("exa", "x-api-key"),
        ("firecrawl", "Authorization"),
    ],
)
def test_the_key_goes_in_the_header_each_provider_expects(
    name: str, header: str
) -> None:
    headers = auth_headers(PROVIDERS[name], "SECRET")

    assert header in headers
    assert "SECRET" in headers[header]


def test_bearer_providers_prefix_the_key() -> None:
    assert auth_headers(PROVIDERS["tavily"], "k")["Authorization"] == "Bearer k"
    assert auth_headers(PROVIDERS["firecrawl"], "k")["Authorization"] == "Bearer k"


def test_searxng_sends_no_credential() -> None:
    """It is normally an instance you host yourself, with no key at all."""
    assert auth_headers(PROVIDERS["searxng"], "") == {}
    assert PROVIDERS["searxng"].needs_key is False


def test_get_providers_send_a_query_string_and_post_providers_send_json() -> None:
    params, body = build_request(PROVIDERS["bing"], "cats", 3)
    assert params == {"q": "cats", "count": 3} and body is None

    params, body = build_request(PROVIDERS["tavily"], "cats", 3)
    assert body == {"query": "cats", "max_results": 3} and params is None


def test_searxng_asks_for_json_and_sends_no_count() -> None:
    """It has no result-count parameter; the cap is applied when parsing."""
    params, _ = build_request(PROVIDERS["searxng"], "cats", 3)

    assert params == {"q": "cats", "format": "json"}


def test_an_unknown_provider_falls_back_rather_than_raising() -> None:
    assert get_provider("not-a-provider").key == "bing"
    assert get_provider(None).key == "bing"


def test_a_provider_needing_no_key_is_configured_without_one() -> None:
    assert is_configured(
        {"enabled": True, "provider": "searxng", "endpoint": "https://s.example/search"}
    )


def test_searxng_still_needs_an_endpoint() -> None:
    """It has no default: there is no such thing as the public SearXNG."""
    assert not is_configured({"enabled": True, "provider": "searxng"})


def test_a_key_provider_is_not_configured_without_one() -> None:
    assert not is_configured({"enabled": True, "provider": "tavily"})
    assert is_configured({"enabled": True, "provider": "tavily", "api_key": "k"})


def test_settings_written_before_providers_existed_still_work() -> None:
    """The old file had `bing_endpoint` / `bing_api_key` and no provider."""
    legacy = {
        "enabled": True,
        "bing_endpoint": "https://api.bing.microsoft.com/v7.0/search",
        "bing_api_key": "k",
    }

    assert is_configured(legacy)


def test_a_self_hosted_endpoint_is_refused_unless_opted_in() -> None:
    with pytest.raises(ResearchError, match="not a public address"):
        validate_endpoint("https://192.168.1.10/search")

    assert validate_endpoint("https://192.168.1.10/search", allow_private=True)


def test_the_opt_in_also_permits_http() -> None:
    """A LAN SearXNG box rarely has a certificate."""
    with pytest.raises(ResearchError):
        validate_endpoint("http://searx.local:8080/search")

    assert validate_endpoint("http://searx.local:8080/search", allow_private=True)


def test_the_opt_in_does_not_excuse_a_nonsense_scheme() -> None:
    for bad in ("file:///etc/passwd", "gopher://x/1", "https:///search"):
        with pytest.raises(ResearchError):
            validate_endpoint(bad, allow_private=True)


def test_searching_a_self_hosted_endpoint_without_the_opt_in_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = {
        "enabled": True,
        "provider": "searxng",
        "endpoint": "http://127.0.0.1:8888/search",
    }

    with pytest.raises(ResearchError):
        search("anything", settings)

    import specy_road.bundled_scripts.brainstorm_research as mod

    class _Resp:
        status_code = 200

        def json(self) -> Any:
            return RESPONSES["searxng"]

    monkeypatch.setattr(mod.requests, "request", lambda *a, **k: _Resp())
    results = search("anything", {**settings, "allow_private_endpoint": True})

    assert [r.url for r in results] == ["https://e/1", "https://e/2"]
