"""The PM GUI brainstorm panel API.

The panel shares its session file and promotion path with the CLI, so what is
worth pinning here is the HTTP surface: that mutations are fingerprint-guarded,
that the mode decides which prompt the model is given, and that the search loop
degrades rather than failing when research is unconfigured.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from tests.helpers import DOGFOOD, script_subprocess_env, use_fake_llm
from tests.support.extracted.brainstorm_chat import REPLY_WITH_IDEAS
from specy_road.gui_app_models import BrainstormTriageBody
from specy_road.gui_app_routes_brainstorm import _apply_triage, _payload
from specy_road.brainstorm_session import BrainstormSession, add_idea
from tests.support.extracted.folded_review_brainstorm import ROOT

RESEARCH_ON = {
    "enabled": True,
    "provider": "bing",
    "endpoint": "https://example.invalid/search",
    "api_key": "k",
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


def test_a_traversing_slug_is_a_400_not_a_crash(api_client: TestClient) -> None:
    """Refused, and refused cleanly — the slug is the caller's input."""
    r = api_client.post(
        "/api/brainstorm/session",
        json={"topic": "x", "slug": "a/../../roadmap/registry"},
        headers=_headers(api_client),
    )

    assert r.status_code == 400
    assert "slug" in r.json()["detail"]


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
    assert research["api_key"] == ""
    assert research["allow_private_endpoint"] is False


def test_research_settings_round_trip_and_obfuscate_the_key(
    api_client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json

    from specy_road import roadmap_gui_settings as m

    monkeypatch.setattr(m, "SETTINGS_DIR", tmp_path / "cfg")
    monkeypatch.setattr(m, "SETTINGS_PATH", tmp_path / "cfg" / "gui-settings.json")

    import os

    r = api_client.put(
        "/api/settings",
        json={
            "inherit_llm": True,
            "llm": {"backend": "anthropic", "anthropic_api_key": "llm-secret"},
            "git_remote": {"repo": "o/r", "token": "git-secret"},
            "pm_gui": {},
            "research": {**RESEARCH_ON, "api_key": "secret-key"},
        },
    )

    assert r.status_code == 200, r.text
    raw = json.loads((tmp_path / "cfg" / "gui-settings.json").read_text())
    assert raw["global"]["research"]["api_key"].startswith("__b64__:")
    assert "secret-key" not in raw["global"]["research"]["api_key"]
    # The page never receives a credential: GET masks every one of them.
    page = api_client.get("/api/settings").json()
    assert not {"llm-secret", "git-secret", "secret-key"} & set(json.dumps(page).split('"'))
    assert page["llm"]["anthropic_api_key"] == page["research"]["api_key"] == "********"
    # Sending the mask back means "the stored one": saving keeps the secrets...
    r = api_client.put("/api/settings", json={k: page[k] for k in (
        "inherit_llm", "llm", "git_remote", "pm_gui", "research")})
    assert r.status_code == 200, r.text
    raw = json.loads((tmp_path / "cfg" / "gui-settings.json").read_text())
    assert "secret-key" not in json.dumps(raw)
    eff = m.effective_settings_for_repo(Path(os.environ["SPECY_ROAD_REPO_ROOT"]))
    assert (eff["llm"]["anthropic_api_key"], eff["git_remote"]["token"],
            eff["research"]["api_key"]) == ("llm-secret", "git-secret", "secret-key")
    # ...and a chat sent with the page's masked settings uses the stored key.
    monkeypatch.delenv("SPECY_ROAD_ANTHROPIC_API_KEY", raising=False)
    used = []
    use_fake_llm(monkeypatch, lambda *_a, **_k: used.append(
        os.environ.get("SPECY_ROAD_ANTHROPIC_API_KEY")) or "ok")
    slug = _session(api_client)["slug"]
    r = api_client.post("/api/brainstorm/chat", headers=_headers(api_client), json={
        "slug": slug, "messages": [{"role": "user", "content": "go"}], "llm": page["llm"]})
    assert r.status_code == 200, r.text
    assert used == ["llm-secret"]


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
    use_fake_llm(monkeypatch, lambda *_a, **_k: REPLY_WITH_IDEAS)
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
    use_fake_llm(monkeypatch, lambda *_a, **_k: REPLY_WITH_IDEAS)
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




def test_a_chat_turn_keeps_ideas_written_while_the_model_was_thinking(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pre-release review: the chat route saved the session it loaded before the LLM call, dropping a shard's idea."""
    slug = _session(api_client)["slug"]

    def reply(*_a, **_k) -> str:
        subprocess.run([sys.executable, "-m", "specy_road.cli", "brainstorm", "add-idea", "--slug", slug,
                        "--title", "From a panel shard"], env=script_subprocess_env(), check=True, capture_output=True)
        return "IDEA: From the chat"

    use_fake_llm(monkeypatch, reply)
    r = api_client.post("/api/brainstorm/chat", json={"slug": slug, "messages": [{"role": "user", "content": "go"}],
                                                      "llm": {}}, headers=_headers(api_client))
    assert r.status_code == 200, r.text
    assert sorted(i["title"] for i in r.json()["session"]["ideas"]) == ["From a panel shard", "From the chat"]



# --- B9, F13 ------------------------------------------------------------------

# One test per finding: a completed worker still owns its leaf; lifecycle transitions are one
# transaction each; the guard refuses shell shapes it cannot follow and `git -C` into another
# tree, and denies a bare commit; an embedded placeholder is refused; the default session id is
# stable across processes and `touch` keeps the paths; a skipped skill is never adopted or
# overwritten; a stale worktree directory is refused; the GUI reports the v2 session and requires
# a reject reason; op ids bind their arguments; signing without a roster key is refused early; a
# foreign skill link is left alone; a dead wrapper frees the leaf; terminate refuses an
# unverifiable pid and does not signal an adopted session; READY binds to the branch; a profile
# path cannot escape the repo; `--harness` cannot override the roster; a plan with no coordinator
# says so; search results are delimited; the verifier's byte cap is a cap.

def test_the_gui_payload_carries_the_v2_session_and_rejects_need_a_reason() -> None:
    session = BrainstormSession(slug="s", topic="t", round=2, profile="technical", panel=3,
                                frame={"outcome": "x"}, allocation="grid")
    add_idea(session, title="One")
    out = _payload(session)
    assert (out["round"], out["profile"], out["panel"], out["frame"], out["allocation"]) == (2, "technical", 3, {"outcome": "x"}, "grid")
    with pytest.raises(Exception, match="needs a reason"):
        _apply_triage(session, BrainstormTriageBody(slug="s", idea_id="B1", status="rejected"))
    _apply_triage(session, BrainstormTriageBody(slug="s", idea_id="B1", status="rejected", reason="not now"))
    assert session.by_id("B1").decision["reason"] == "not now"



# --- F3 --------------------------------------------------------------------


# Every diverge prompt and the copy-paste prompt carry a write allow-list, so a divergence agent
# is told not to build what it proposes.
# The GUI payload carries the planned round count, not just the current round.
# The GUI converge pass is advisory — nothing structured is persisted, and the docs say so.
# Malformed overlap, URL and stance fail at the boundary with `BrainstormError` instead of
# corrupting the session or raising `KeyError`; the parser help no longer says `start` researches.

def test_gui_payload_carries_the_planned_round_count() -> None:
    payload = _payload(BrainstormSession(slug="x", topic="t", round=2, rounds=7))
    assert payload["round"] == 2
    assert payload["rounds"] == 7



# --- F7 / Question 3 -------------------------------------------------------


@pytest.fixture()
def api_client_folded(repo: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("SPECY_ROAD_REPO_ROOT", str(repo))
    from specy_road.gui_app import create_app

    return TestClient(create_app())



def test_gui_converge_is_advisory_and_persists_nothing_structured(
    api_client_folded: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The decision: no structured converge protocol in the GUI; docs say advisory."""
    use_fake_llm(
        monkeypatch,
        lambda *_a, **_k: "B1: strong — Principle 3; cluster C1; overlaps M1.1 (adjacent)\nIDEA: sneaky\n",
    )
    fingerprint = api_client_folded.get("/api/roadmap").json()["fingerprint"]
    headers = {"X-PM-Gui-Fingerprint": str(fingerprint)}
    slug = api_client_folded.post(
        "/api/brainstorm/session", json={"topic": "Expand payments", "under": "M1"}, headers=headers,
    ).json()["slug"]
    api_client_folded.post(
        "/api/brainstorm/idea",
        json={"slug": slug, "title": "Stored vault"},
        headers=headers,
    )
    api_client_folded.post(
        "/api/brainstorm/session",
        json={"slug": slug, "mode": "roadmap"},
        headers=headers,
    )

    r = api_client_folded.post(
        "/api/brainstorm/chat",
        json={"slug": slug, "messages": [{"role": "user", "content": "assess"}], "llm": {}},
        headers=headers,
    )

    assert r.status_code == 200, r.text
    assert r.json()["ideas"] == []
    (idea,) = r.json()["session"]["ideas"]
    assert idea["recommendation"] is None
    assert not idea.get("cluster_id") and not idea.get("overlap") and not idea.get("critic")



@pytest.mark.repo
def test_gui_docs_say_converge_is_advisory_and_route_to_revise() -> None:
    doc = (ROOT / "docs" / "pm-gui.md").read_text(encoding="utf-8")
    assert "advisory only" in doc.lower()
    assert "specy-road brainstorm revise" in doc
    assert "ordered by the model's verdict" not in doc
