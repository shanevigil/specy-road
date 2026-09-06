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

from tests.helpers import DOGFOOD
from tests.test_brainstorm_chat import REPLY_WITH_IDEAS

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
    r = api_client.post(
        "/api/research/test",
        json={"research": {"enabled": False}},
        headers=_headers(api_client),
    )

    assert r.status_code == 400
    assert "Settings" in r.json()["detail"]


def test_testing_an_endpoint_needs_the_write_header(api_client: TestClient) -> None:
    """It fetches a caller-supplied URL, so it is guarded like a write."""
    r = api_client.post("/api/research/test", json={"research": RESEARCH_ON})

    assert r.status_code == 428


def test_chatting_puts_the_models_ideas_on_the_board(
    api_client: TestClient, monkeypatch
) -> None:
    """The panel's whole point: without this, triage and promote stay empty."""
    import specy_road.bundled_scripts.brainstorm_chat as mod

    monkeypatch.setattr(mod, "complete_chat", lambda *_a, **_k: REPLY_WITH_IDEAS)
    slug = _session(api_client)["slug"]

    r = api_client.post(
        "/api/brainstorm/chat",
        json={
            "slug": slug,
            "messages": [{"role": "user", "content": "go"}],
            "llm": {},
        },
        headers=_headers(api_client),
    )

    assert r.status_code == 200, r.text
    titles = [i["title"] for i in r.json()["session"]["ideas"]]
    assert titles == ["Stored payment vault", "Chargeback exposure review"]
    # Persisted, not just echoed: reopening the session has to show them.
    reopened = api_client.get(f"/api/brainstorm/session?slug={slug}").json()
    assert [i["title"] for i in reopened["ideas"]] == titles


def test_converging_does_not_quietly_add_ideas(
    api_client: TestClient, monkeypatch
) -> None:
    import specy_road.bundled_scripts.brainstorm_chat as mod

    monkeypatch.setattr(mod, "complete_chat", lambda *_a, **_k: REPLY_WITH_IDEAS)
    slug = _session(api_client, mode="roadmap")["slug"]

    r = api_client.post(
        "/api/brainstorm/chat",
        json={
            "slug": slug,
            "messages": [{"role": "user", "content": "go"}],
            "llm": {},
        },
        headers=_headers(api_client),
    )

    assert r.json()["session"]["ideas"] == []


