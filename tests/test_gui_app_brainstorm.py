"""The PM GUI brainstorm panel API.

The panel shares its session file and promotion path with the CLI, so what is
worth pinning here is the HTTP surface: that mutations are fingerprint-guarded,
that the mode decides which prompt the model is given, and that the search loop
degrades rather than failing when research is unconfigured.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from specy_road.bundled_scripts.brainstorm_chat import (
    NO_RESEARCH_NOTICE,
    RESEARCH_INSTRUCTIONS,
    chat_turn,
    extract_queries,
    system_prompt_for,
)
from specy_road.bundled_scripts.brainstorm_research import (
    ResearchError,
    is_configured,
    search,
)
from tests.helpers import DOGFOOD

RESEARCH_ON = {
    "enabled": True,
    "bing_endpoint": "https://example.invalid/search",
    "bing_api_key": "k",
    "max_results": "3",
}


@pytest.fixture()
def api_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    dest = tmp_path / "dogfood"
    shutil.copytree(DOGFOOD, dest)
    monkeypatch.setenv("SPECY_ROAD_REPO_ROOT", str(dest))
    from specy_road.gui_app import create_app

    return TestClient(create_app())


def _headers(client: TestClient) -> dict[str, str]:
    r = client.get("/api/roadmap")
    return {"X-PM-Gui-Fingerprint": str(r.json()["fingerprint"])}


def _session(client: TestClient, **kw) -> dict:
    body = {"topic": "How do we expand payments?", "under": "M1", **kw}
    r = client.post("/api/brainstorm/session", json=body, headers=_headers(client))
    assert r.status_code == 200, r.text
    return r.json()


def _idea(client: TestClient, slug: str, title: str, **kw) -> dict:
    r = client.post(
        "/api/brainstorm/idea",
        json={"slug": slug, "title": title, **kw},
        headers=_headers(client),
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_creating_a_session_derives_its_slug(api_client: TestClient) -> None:
    payload = _session(api_client)

    assert payload["slug"] == "how-do-we-expand-payments"
    assert payload["under"] == "M1"
    assert payload["mode"] == "brainstorm"


def test_a_session_without_a_topic_or_slug_is_refused(api_client: TestClient) -> None:
    r = api_client.post(
        "/api/brainstorm/session", json={}, headers=_headers(api_client)
    )

    assert r.status_code == 400


def test_mutations_require_the_fingerprint_header(api_client: TestClient) -> None:
    r = api_client.post("/api/brainstorm/session", json={"topic": "x"})

    assert r.status_code in (412, 428)


def test_reading_an_unknown_session_is_a_404(api_client: TestClient) -> None:
    r = api_client.get("/api/brainstorm/session", params={"slug": "ghost"})

    assert r.status_code == 404


def test_sessions_are_listed(api_client: TestClient) -> None:
    _session(api_client)

    r = api_client.get("/api/brainstorm/sessions")

    assert r.json()["slugs"] == ["how-do-we-expand-payments"]


def test_ideas_accumulate_with_allocated_ids(api_client: TestClient) -> None:
    slug = _session(api_client)["slug"]

    _idea(api_client, slug, "One")
    payload = _idea(api_client, slug, "Two", evidence=["https://x"], kind="risk")

    assert [i["id"] for i in payload["ideas"]] == ["B1", "B2"]
    assert payload["ideas"][1]["kind"] == "risk"
    assert payload["ideas"][1]["evidence"] == ["https://x"]


def test_triage_accepts_an_idea(api_client: TestClient) -> None:
    slug = _session(api_client)["slug"]
    _idea(api_client, slug, "One")

    r = api_client.post(
        "/api/brainstorm/triage",
        json={"slug": slug, "idea_id": "B1", "status": "accepted"},
        headers=_headers(api_client),
    )

    assert r.json()["ideas"][0]["status"] == "accepted"
    assert r.json()["pending_promotion"] == ["B1"]


def test_a_recommendation_alone_leaves_the_status_alone(api_client: TestClient) -> None:
    """Same rule as the CLI: the model advises, the PM decides."""
    slug = _session(api_client)["slug"]
    _idea(api_client, slug, "One")

    r = api_client.post(
        "/api/brainstorm/triage",
        json={"slug": slug, "idea_id": "B1", "recommendation": "strong"},
        headers=_headers(api_client),
    )

    idea = r.json()["ideas"][0]
    assert idea["recommendation"] == "strong"
    assert idea["status"] == "proposed"


def test_editing_an_idea_marks_it_revised(api_client: TestClient) -> None:
    slug = _session(api_client)["slug"]
    _idea(api_client, slug, "One")

    r = api_client.post(
        "/api/brainstorm/triage",
        json={"slug": slug, "idea_id": "B1", "title": "Sharper"},
        headers=_headers(api_client),
    )

    assert r.json()["ideas"][0]["title"] == "Sharper"
    assert r.json()["ideas"][0]["status"] == "revised"


def test_triaging_an_unknown_idea_is_a_400(api_client: TestClient) -> None:
    slug = _session(api_client)["slug"]

    r = api_client.post(
        "/api/brainstorm/triage",
        json={"slug": slug, "idea_id": "B9", "status": "accepted"},
        headers=_headers(api_client),
    )

    assert r.status_code == 400


def test_promote_writes_nodes_and_reports_them(api_client: TestClient) -> None:
    slug = _session(api_client)["slug"]
    _idea(api_client, slug, "Stored payment vault")
    api_client.post(
        "/api/brainstorm/triage",
        json={"slug": slug, "idea_id": "B1", "status": "accepted"},
        headers=_headers(api_client),
    )

    r = api_client.post(
        "/api/brainstorm/promote",
        json={"slug": slug},
        headers=_headers(api_client),
    )

    assert r.status_code == 200, r.text
    promoted = r.json()["promoted"]
    assert len(promoted) == 1
    assert promoted[0]["parent_id"] == "M1"
    nodes = api_client.get("/api/roadmap").json()["nodes"]
    assert any(n["node_key"] == promoted[0]["node_key"] for n in nodes)


def test_a_dry_run_promotion_changes_nothing(api_client: TestClient) -> None:
    slug = _session(api_client)["slug"]
    _idea(api_client, slug, "One")
    api_client.post(
        "/api/brainstorm/triage",
        json={"slug": slug, "idea_id": "B1", "status": "accepted"},
        headers=_headers(api_client),
    )
    before = len(api_client.get("/api/roadmap").json()["nodes"])

    r = api_client.post(
        "/api/brainstorm/promote",
        json={"slug": slug, "dry_run": True},
        headers=_headers(api_client),
    )

    assert r.json()["dry_run"] is True
    assert len(api_client.get("/api/roadmap").json()["nodes"]) == before


def test_an_unusable_anchor_is_a_400(api_client: TestClient) -> None:
    slug = _session(api_client)["slug"]
    _idea(api_client, slug, "One")
    api_client.post(
        "/api/brainstorm/triage",
        json={"slug": slug, "idea_id": "B1", "status": "accepted"},
        headers=_headers(api_client),
    )

    r = api_client.post(
        "/api/brainstorm/promote",
        json={"slug": slug, "under": "M404"},
        headers=_headers(api_client),
    )

    assert r.status_code == 400


def test_settings_carry_the_research_block(api_client: TestClient) -> None:
    r = api_client.get("/api/settings")

    research = r.json()["research"]
    assert research["provider"] == "bing"
    assert research["enabled"] is False
    assert research["bing_api_key"] == ""


def test_research_settings_round_trip_and_obfuscate_the_key(
    api_client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json

    from specy_road.bundled_scripts import roadmap_gui_settings as m

    monkeypatch.setattr(m, "SETTINGS_DIR", tmp_path / "cfg")
    monkeypatch.setattr(m, "SETTINGS_PATH", tmp_path / "cfg" / "gui-settings.json")

    r = api_client.put(
        "/api/settings",
        json={
            "inherit_llm": True,
            "llm": {},
            "git_remote": {},
            "pm_gui": {},
            "research": {**RESEARCH_ON, "bing_api_key": "secret-key"},
        },
    )

    assert r.status_code == 200, r.text
    raw = json.loads((tmp_path / "cfg" / "gui-settings.json").read_text())
    assert raw["global"]["research"]["bing_api_key"].startswith("__b64__:")
    assert "secret-key" not in raw["global"]["research"]["bing_api_key"]
    assert api_client.get("/api/settings").json()["research"]["bing_api_key"] == (
        "secret-key"
    )


def test_testing_an_unconfigured_endpoint_is_a_400(api_client: TestClient) -> None:
    r = api_client.post("/api/research/test", json={"research": {"enabled": False}})

    assert r.status_code == 400
    assert "Settings" in r.json()["detail"]


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
