"""The chat and research protocols: line parsing, the search loop, endpoints.

These are the text contracts the GUI panel rests on — how a reply becomes
ideas, how a search round trips — and none of them need a running app. The
route-level tests live in ``test_gui_app_brainstorm``.
"""

from __future__ import annotations

import pytest

from specy_road.bundled_scripts.brainstorm_chat import (
    NO_RESEARCH_NOTICE,
    RESEARCH_INSTRUCTIONS,
    chat_turn,
    extract_ideas,
    extract_queries,
    system_prompt_for,
)
from specy_road.bundled_scripts.brainstorm_research import (
    DEFAULT_ENDPOINT,
    ResearchError,
    is_configured,
    search,
    validate_endpoint,
)

RESEARCH_ON = {
    "enabled": True,
    "bing_endpoint": DEFAULT_ENDPOINT,
    "bing_api_key": "k",
    "max_results": 3,
}


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://169.254.169.254/latest/meta-data/",
        "https://127.0.0.1:9999/search",
        "https://localhost/search",
        "https://192.168.1.1/search",
        "file:///etc/passwd",
        "https:///search",
    ],
)
def test_the_endpoint_cannot_point_at_this_machine(endpoint: str) -> None:
    """The GUI is reachable from any page in the browser, so an unchecked
    endpoint turns search into a probe of the host's own network."""
    with pytest.raises(ResearchError):
        validate_endpoint(endpoint)


def test_the_default_endpoint_is_accepted() -> None:
    assert validate_endpoint(DEFAULT_ENDPOINT) == DEFAULT_ENDPOINT


def test_research_is_only_configured_when_complete() -> None:
    assert is_configured(RESEARCH_ON)
    assert not is_configured({**RESEARCH_ON, "enabled": False})
    assert not is_configured({**RESEARCH_ON, "bing_api_key": ""})
    assert not is_configured(None)


def test_searching_without_a_key_names_the_missing_piece() -> None:
    with pytest.raises(ResearchError, match="API key"):
        search("anything", {**RESEARCH_ON, "bing_api_key": ""})


def test_the_system_prompt_states_which_research_exists() -> None:
    """A model told it can search when it cannot will invent sources."""
    assert RESEARCH_INSTRUCTIONS in system_prompt_for("BASE", RESEARCH_ON)
    assert NO_RESEARCH_NOTICE in system_prompt_for("BASE", None)


REPLY_WITH_IDEAS = """Three angles worth considering.

IDEA: Stored payment vault
WHY: Repeat buyers abandon at card entry.
KIND: feature
EFFORT: M
SOURCE: https://example.com/cart-abandonment

Some prose in between that is not part of any block.

IDEA: Chargeback exposure review
KIND: risk
EFFORT: S

IDEA:
WHY: a block with no title should be dropped
"""


def test_idea_blocks_are_parsed_out_of_a_reply() -> None:
    ideas = extract_ideas(REPLY_WITH_IDEAS)

    assert [i["title"] for i in ideas] == [
        "Stored payment vault",
        "Chargeback exposure review",
    ]
    assert ideas[0]["kind"] == "feature"
    assert ideas[0]["effort"] == "M"
    assert ideas[0]["evidence"] == ["https://example.com/cart-abandonment"]
    assert ideas[0]["rationale"].startswith("Repeat buyers")
    # No SOURCE line, and prose between blocks must not leak into the next one.
    assert ideas[1]["evidence"] == []
    assert ideas[1]["kind"] == "risk"


def test_an_unknown_kind_falls_back_rather_than_failing() -> None:
    ideas = extract_ideas("IDEA: Something\nKIND: wishlist")

    assert ideas[0]["kind"] == "feature"


def test_ideas_are_only_captured_when_asked_for(monkeypatch) -> None:
    """The CLI's agent records ideas by running the command, so it opts out."""
    import specy_road.bundled_scripts.brainstorm_chat as mod

    monkeypatch.setattr(mod, "complete_chat", lambda *_a, **_k: "IDEA: One")

    without = chat_turn([{"role": "user", "content": "go"}], system_prompt="B")
    with_capture = chat_turn(
        [{"role": "user", "content": "go"}], system_prompt="B", capture_ideas=True
    )

    assert without["ideas"] == []
    assert [i["title"] for i in with_capture["ideas"]] == ["One"]


def test_search_requests_are_parsed_and_capped() -> None:
    reply = "SEARCH: one\nSEARCH: two\nSEARCH: one\nSEARCH: three\nSEARCH: four\nSEARCH: five"

    assert extract_queries(reply) == ["one", "two", "three", "four"]


def test_a_reply_with_prose_is_not_a_search_request(monkeypatch) -> None:
    """Only a turn that is *only* SEARCH lines triggers the loop."""
    import specy_road.bundled_scripts.brainstorm_chat as mod

    monkeypatch.setattr(
        mod, "complete_chat", lambda *_a, **_k: "Here is an idea.\nSEARCH: unused"
    )

    result = chat_turn([{"role": "user", "content": "go"}], system_prompt="B",
                       research=RESEARCH_ON)

    assert result["searched"] == []
    assert "Here is an idea." in result["reply"]


def test_the_search_loop_feeds_results_back(monkeypatch) -> None:
    import specy_road.bundled_scripts.brainstorm_chat as mod

    replies = iter(["SEARCH: payments trends", "Two ideas, sourced."])
    monkeypatch.setattr(mod, "complete_chat", lambda *_a, **_k: next(replies))
    monkeypatch.setattr(
        mod,
        "search",
        lambda q, s: [mod.SearchResult(title="T", url="https://u", snippet="S")],
    )

    result = chat_turn([{"role": "user", "content": "go"}], system_prompt="B",
                       research=RESEARCH_ON)

    assert result["searched"] == ["payments trends"]
    assert result["sources"] == ["https://u"]
    assert result["reply"] == "Two ideas, sourced."
    assert any("Search results:" in m["content"] for m in result["messages"])


def test_a_failing_search_becomes_text_the_model_can_read(monkeypatch) -> None:
    """A dead endpoint should not abort the brainstorm."""
    import specy_road.bundled_scripts.brainstorm_chat as mod

    replies = iter(["SEARCH: anything", "Answered from memory."])
    monkeypatch.setattr(mod, "complete_chat", lambda *_a, **_k: next(replies))

    def _boom(_q, _s):
        raise ResearchError("endpoint is down")

    monkeypatch.setattr(mod, "search", _boom)

    result = chat_turn([{"role": "user", "content": "go"}], system_prompt="B",
                       research=RESEARCH_ON)

    assert result["reply"] == "Answered from memory."
    assert any("endpoint is down" in m["content"] for m in result["messages"])


def test_the_search_loop_is_bounded(monkeypatch) -> None:
    import specy_road.bundled_scripts.brainstorm_chat as mod

    calls = {"n": 0}

    def _always_search(*_a, **_k):
        calls["n"] += 1
        return "SEARCH: again"

    monkeypatch.setattr(mod, "complete_chat", _always_search)
    monkeypatch.setattr(mod, "search", lambda _q, _s: [])

    chat_turn([{"role": "user", "content": "go"}], system_prompt="B",
              research=RESEARCH_ON)

    assert calls["n"] == mod.MAX_SEARCH_ROUNDS + 1


def test_search_lines_are_ignored_when_research_is_off(monkeypatch) -> None:
    import specy_road.bundled_scripts.brainstorm_chat as mod

    monkeypatch.setattr(mod, "complete_chat", lambda *_a, **_k: "SEARCH: nope")

    result = chat_turn([{"role": "user", "content": "go"}], system_prompt="B",
                       research=None)

    assert result["searched"] == []
    assert result["reply"] == "SEARCH: nope"
