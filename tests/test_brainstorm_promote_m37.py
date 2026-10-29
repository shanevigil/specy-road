"""M3.7: promote validates once, capped codenames, goal, order, missing-field list."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from specy_road.bundled_scripts.brainstorm_promote import (
    PROMOTE_CODENAME_MAX_WORDS,
    promote_session,
)
from specy_road.bundled_scripts.brainstorm_session import (
    BrainstormSession,
    add_idea,
)
from specy_road.bundled_scripts.roadmap_load import load_roadmap
from tests.helpers import DOGFOOD


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    dest = tmp_path / "repo"
    shutil.copytree(DOGFOOD, dest)
    return dest


def _by_id(root: Path) -> dict[str, dict]:
    return {n["id"]: n for n in load_roadmap(root)["nodes"]}


def test_promote_runs_full_validation_once_for_a_batch(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import specy_road.bundled_scripts.brainstorm_promote as mod

    s = BrainstormSession(slug="pay", topic="t", under="M1")
    for title in ("One", "Two", "Three"):
        add_idea(s, title=title).status = "accepted"
    calls = {"n": 0}
    real = mod.run_validate_raise

    def _count(*a, **k):
        calls["n"] += 1
        return real(*a, **k)

    monkeypatch.setattr(mod, "run_validate_raise", _count)
    promote_session(repo, s)
    assert calls["n"] == 1


def test_promote_derives_codename_from_the_first_four_title_words(repo: Path) -> None:
    s = BrainstormSession(slug="pay", topic="t", under="M1")
    words = [f"word{i}" for i in range(PROMOTE_CODENAME_MAX_WORDS + 3)]
    idea = add_idea(s, title=" ".join(words))
    idea.status = "accepted"

    node_id = promote_session(repo, s)[0].node_id

    assert _by_id(repo)[node_id]["codename"] == "-".join(words[:PROMOTE_CODENAME_MAX_WORDS])


def test_revise_codename_on_the_idea_wins_over_title_derivation(repo: Path) -> None:
    s = BrainstormSession(slug="pay", topic="t", under="M1")
    idea = add_idea(s, title="Some Long Title That Would Slug Longer")
    idea.codename = "pm-picked-slug"
    idea.status = "accepted"

    node_id = promote_session(repo, s)[0].node_id

    assert _by_id(repo)[node_id]["codename"] == "pm-picked-slug"


def test_promote_copies_hypothesis_to_goal_and_orders_siblings_by_accept_time(
    repo: Path,
) -> None:
    s = BrainstormSession(slug="pay", topic="t", under="M1")
    first = add_idea(s, title="First")
    first.status = "accepted"
    first.decision = {"status": "accepted", "decided_at": "2026-01-02"}
    first.hypothesis = "Latency drops because we cache"
    second = add_idea(s, title="Second")
    second.status = "accepted"
    second.decision = {"status": "accepted", "decided_at": "2026-01-01"}

    results = promote_session(repo, s)

    assert len(results) == 2
    nodes = _by_id(repo)
    second_id = next(r.node_id for r in results if r.title == "Second")
    first_id = next(r.node_id for r in results if r.title == "First")
    assert nodes[second_id]["sibling_order"] == 1
    assert nodes[first_id]["sibling_order"] == 2
    assert nodes[first_id]["goal"] == "Latency drops because we cache"


def test_promote_lists_nodes_still_missing_acceptance_or_touch_zones(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    s = BrainstormSession(slug="pay", topic="t", under="M1")
    add_idea(s, title="Needs authoring").status = "accepted"

    results = promote_session(repo, s)

    err = capsys.readouterr().err
    assert "still missing acceptance or touch_zones" in err
    assert results[0].node_id in err
