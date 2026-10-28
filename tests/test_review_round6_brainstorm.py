"""Review round 6, brainstorm items: B8, F3, F7 (Question 3), F8.

B8: every diverge prompt and the copy-paste prompt carry a write allow-list,
so a divergence agent is told not to build what it proposes. F3: the GUI
payload carries the planned round count, not just the current round. F7:
the GUI converge pass is advisory — nothing structured is persisted, and
the docs say so. F8: malformed overlap, URL and stance fail at the boundary
with ``BrainstormError`` instead of corrupting the session or raising
``KeyError``; the parser help no longer says ``start`` researches.
"""

from __future__ import annotations

import contextlib
import io
import shutil
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from tests.helpers import DOGFOOD

from specy_road.bundled_scripts import brainstorm_cli
from specy_road.bundled_scripts.brainstorm_fields import parse_overlap, source_record
from specy_road.bundled_scripts.brainstorm_prompt import (
    render_brainstorm_prompt,
    render_recommend_prompt,
    render_shard_prompt,
)
from specy_road.bundled_scripts.brainstorm_session import (
    BrainstormError,
    BrainstormSession,
    add_idea,
    idea_from_dict,
    read_session,
)
from specy_road.gui_app_routes_brainstorm import _payload

ROOT = Path(__file__).resolve().parents[1]
SLUG = "how-do-we-expand-payments"
FORBIDDEN = ("planning/", "roadmap/", "registry.yaml", "shared/", "Do not edit code")


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    dest = tmp_path / "repo"
    shutil.copytree(DOGFOOD, dest)
    return dest


def _cli(repo: Path, *args: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            brainstorm_cli.main([*args, "--repo-root", str(repo)])
            code = 0
        except SystemExit as e:
            code = int(e.code or 0)
    return code, out.getvalue(), err.getvalue()


def _started(repo: Path, *extra: str) -> BrainstormSession:
    code, _out, err = _cli(repo, "start", "--topic", "How do we expand payments?", "--under", "M1", *extra)
    assert code == 0, err
    return read_session(repo, SLUG)


# --- B8 --------------------------------------------------------------------


def test_round_one_prompt_carries_the_write_allow_list(repo: Path) -> None:
    text = render_brainstorm_prompt(repo, _started(repo), count=5)
    assert "## What you may write" in text
    for needle in FORBIDDEN:
        assert needle in text, needle
    assert "`add-idea`, `add-evidence`, and `revise`" in text


def test_later_rounds_and_shards_carry_the_allow_list_too(repo: Path) -> None:
    session = _started(repo, "--panel", "2")
    add_idea(session, title="Stored vault")
    session.round = 2
    later = render_brainstorm_prompt(repo, session, count=5)
    shard = render_shard_prompt(repo, session, count=5, shard=1, total=2)
    for text in (later, shard):
        assert "## What you may write" in text
        assert "registry.yaml" in text


def test_converge_prompt_still_forbids_new_ideas_but_is_not_a_diverge_prompt(repo: Path) -> None:
    """The allow-list is a diverge rule; converge keeps its own 'no new ideas' rule."""
    text = render_recommend_prompt(repo, _started(repo))
    assert "must not add new ideas" in text


def test_suggested_prompt_and_docs_mirror_the_allow_list() -> None:
    prompt = (ROOT / "suggested_prompts" / "brainstorm-roadmap.md").read_text(encoding="utf-8")
    doc = (ROOT / "docs" / "brainstorming.md").read_text(encoding="utf-8")
    for text in (prompt, doc):
        assert "## What" in text and "may write" in text
        for needle in ("planning/", "registry.yaml", "shared/", "edit code"):
            assert needle in text, needle
    assert "Do not implement an idea during the session" in prompt


# --- F3 --------------------------------------------------------------------


def test_gui_payload_carries_the_planned_round_count() -> None:
    payload = _payload(BrainstormSession(slug="x", topic="t", round=2, rounds=7))
    assert payload["round"] == 2
    assert payload["rounds"] == 7


# --- F7 / Question 3 -------------------------------------------------------


@pytest.fixture()
def api_client(repo: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("SPECY_ROAD_REPO_ROOT", str(repo))
    from specy_road.gui_app import create_app

    return TestClient(create_app())


def test_gui_converge_is_advisory_and_persists_nothing_structured(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The decision: no structured converge protocol in the GUI; docs say advisory."""
    import specy_road.bundled_scripts.brainstorm_chat as mod

    monkeypatch.setattr(
        mod, "complete_chat",
        lambda *_a, **_k: "B1: strong — Principle 3; cluster C1; overlaps M1.1 (adjacent)\nIDEA: sneaky\n",
    )
    headers = {"X-PM-Gui-Fingerprint": str(api_client.get("/api/roadmap").json()["fingerprint"])}
    slug = api_client.post(
        "/api/brainstorm/session", json={"topic": "Expand payments", "under": "M1"}, headers=headers,
    ).json()["slug"]
    api_client.post("/api/brainstorm/idea", json={"slug": slug, "title": "Stored vault"}, headers=headers)
    api_client.post("/api/brainstorm/session", json={"slug": slug, "mode": "roadmap"}, headers=headers)

    r = api_client.post(
        "/api/brainstorm/chat",
        json={"slug": slug, "messages": [{"role": "user", "content": "assess"}], "llm": {}},
        headers=headers,
    )

    assert r.status_code == 200, r.text
    assert r.json()["ideas"] == []
    (idea,) = r.json()["session"]["ideas"]
    assert idea["recommendation"] is None
    assert not idea.get("cluster_id") and not idea.get("overlap") and not idea.get("critic")


def test_gui_docs_say_converge_is_advisory_and_route_to_revise() -> None:
    doc = (ROOT / "docs" / "pm-gui-brainstorm.md").read_text(encoding="utf-8")
    assert "advisory only" in doc.lower()
    assert "specy-road brainstorm revise" in doc
    assert "ordered by the model's verdict" not in doc


# --- F8 --------------------------------------------------------------------


def test_revise_rejects_an_overlap_without_a_node_id(repo: Path) -> None:
    session = _started(repo)
    add_idea(session, title="Stored vault")
    from specy_road.bundled_scripts.brainstorm_session import write_session

    write_session(repo, session)

    code, _out, err = _cli(repo, "revise", "B1", "--overlap", ":adjacent")

    assert code == 1
    assert "node id" in err
    assert read_session(repo, SLUG).by_id("B1").overlap == []   # nothing written; file still reads


@pytest.mark.parametrize("text", ["", ":", "  :prerequisite"])
def test_parse_overlap_needs_a_node_id(text: str) -> None:
    with pytest.raises(BrainstormError, match="node id"):
        parse_overlap(text)


def test_add_evidence_with_an_empty_url_is_a_brainstorm_error(repo: Path) -> None:
    session = _started(repo)
    add_idea(session, title="Stored vault")
    from specy_road.bundled_scripts.brainstorm_session import write_session

    write_session(repo, session)

    code, _out, err = _cli(repo, "add-evidence", "B1", "--url", "", "--quote", "q")

    assert code == 1
    assert "--url is required" in err
    assert read_session(repo, SLUG).by_id("B1").sources == []


@pytest.mark.parametrize("url", ["", "   "])
def test_source_record_needs_a_url(url: str) -> None:
    with pytest.raises(BrainstormError, match="--url is required"):
        source_record(url, quote="q")


def test_a_loaded_source_with_an_unknown_stance_is_rejected() -> None:
    with pytest.raises(BrainstormError, match="stance 'maybe'"):
        idea_from_dict({"id": "B1", "title": "t", "sources": [{"url": "https://x", "stance": "maybe"}]})
    ok = idea_from_dict({"id": "B1", "title": "t", "sources": [{"url": "https://x", "stance": "against"}]})
    assert ok.sources[0]["stance"] == "against"


def test_start_help_no_longer_claims_research(repo: Path) -> None:
    _code, out, _err = _cli(repo, "-h")
    flat = " ".join(out.split())   # argparse wraps the description
    assert "no research in round 1" in flat
    assert "Socratic questioning, research)" not in flat
