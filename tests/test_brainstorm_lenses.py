"""Lenses from the frame, the personal profile, and the ranked node list in the recommend prompt.

The personas and directions the diverge prompts hand out come from the
frame's ``served`` answer once it is recorded, so a single-author tool is not
brainstormed by a procurement officer; ``--profile personal`` is the lens set
for such tools. The recommend prompt lists the phases plus the nodes the
search index ranks closest to the idea titles, and every node only when the
index cannot rank.
"""

from __future__ import annotations

import contextlib
import io
import shutil
from pathlib import Path

import pytest

from tests.helpers import DOGFOOD

from specy_road import search_index
from specy_road.bundled_scripts import brainstorm_cli
from specy_road.bundled_scripts.brainstorm_lenses import (
    DIRECTIONS,
    OPERATORS,
    directions_for,
    operators_for,
    served_answer,
)
from specy_road.bundled_scripts.brainstorm_prompt import (
    render_brainstorm_prompt,
    render_recommend_prompt,
    render_shard_prompt,
)
from specy_road.bundled_scripts.brainstorm_session import BrainstormSession, add_idea, read_session

SLUG = "how-do-we-expand-payments"


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


def _prompt(repo: Path, pass_name: str = "r1") -> str:
    return (repo / "work" / f"brainstorm-{SLUG}-{pass_name}-prompt.md").read_text(encoding="utf-8")


# --- A1: personas and directions from `served`, the personal profile -------

def test_served_answer_drops_the_assumed_marker() -> None:
    assert served_answer({}) == ""
    assert served_answer({"served": "assumed: the solo author"}) == "the solo author"
    assert served_answer({"served": "  ops teams at SMBs "}) == "ops teams at SMBs"


def test_without_a_frame_the_product_text_is_unchanged() -> None:
    assert OPERATORS == operators_for("product")
    assert "a procurement officer at a regulated buyer" in OPERATORS[0][1]
    assert DIRECTIONS[0] == "user segments" and DIRECTIONS == directions_for("product")


def test_round_one_says_the_personas_are_placeholders_until_served_is_recorded(repo: Path) -> None:
    session = BrainstormSession(slug="s", topic="t")
    assert "The personas above are placeholders" in render_brainstorm_prompt(repo, session, count=5)
    session.frame["served"] = "assumed: the solo author"
    assert "placeholders" not in render_brainstorm_prompt(repo, session, count=5)


def test_recorded_served_answer_drives_personas_and_directions(repo: Path) -> None:
    code, _out, err = _cli(repo, "start", "--topic", "How do we expand payments?", "--panel", "2")
    assert code == 0, err
    code, _out, err = _cli(repo, "frame", "--answer", "served=assumed: night-market stall owners; not banks")
    assert code == 0, err
    shard = _prompt(repo, "r1-s1")   # `frame` rewrites the shard prompts
    assert "drawn from who the frame says is served — night-market stall owners; not banks —" in shard
    assert "procurement officer" not in shard
    assert "**Directions:** segments of who is served (night-market stall owners; not banks);" in shard
    # A shard with no allocation cell gets the first operator and direction, both from `served`.
    assert "- **Direction:** segments of who is served (night-market stall owners; not banks)" in shard
    assert "- **Operator:** Ordinary personas — Generate as three specific, ordinary people drawn" in shard


def test_personal_profile_is_a_lens_set_for_single_author_tools(repo: Path) -> None:
    code, out, err = _cli(repo, "start", "--topic", "How do we expand payments?", "--profile", "personal")
    assert code == 0 and "profile personal" in out, err
    assert read_session(repo, SLUG).profile == "personal"
    text = _prompt(repo)
    assert "Friction log" in text and "Future self" in text and "SCAMPER" not in text
    assert "the author six months from now" in text and "procurement officer" not in text
    assert "**Directions:** daily use; setup and maintenance; the author's future self;" in text
    assert "business model" not in text and "--kind feature" in text


def test_personal_profile_with_served_still_names_the_served_people(repo: Path) -> None:
    session = BrainstormSession(slug="s", topic="t", profile="personal", panel=1,
                                frame={"served": "me, on my laptop"})
    text = render_shard_prompt(repo, session, count=5, shard=1, total=1)
    assert "served — me, on my laptop —" in text and "a friend who borrows" not in text
    assert "- **Direction:** daily use" in text


# --- A2: ranked node list in the recommend prompt ---------------------------

def _recommend_session(*titles: str) -> BrainstormSession:
    session = BrainstormSession(slug="s", topic="t")
    for title in titles:
        add_idea(session, title=title)
    return session


def _inventory(text: str) -> str:
    return text.split("## What already exists", 1)[1].split("## The ideas to assess", 1)[0]


def test_recommend_lists_phases_plus_the_nodes_closest_to_the_ideas(repo: Path) -> None:
    text = _inventory(render_recommend_prompt(repo, _recommend_session(
        "Shared contracts and an ADR skeleton", "Run the roadmap validator in CI")))
    assert "**Phases:**" in text and "`M0` Foundation" in text and "`M1` Implementation track" in text
    assert "**Nodes closest to the ideas**" in text
    closest = text.split("**Nodes closest to the ideas**", 1)[1]
    assert "`M0.1` Establish shared contracts" in closest and "`M0.2` Roadmap validator in CI" in closest
    assert "`M0` Foundation" not in closest   # phases are listed once, above
    assert "specy-road search" in text


def test_recommend_leaves_out_nodes_no_idea_is_near(repo: Path) -> None:
    text = _inventory(render_recommend_prompt(repo, _recommend_session("Roadmap validator in CI")))
    assert "`M0.2` Roadmap validator in CI" in text
    assert "`M2` testing" not in text
    assert "of 6 nodes" in text and "This is 6 of 6" not in text


def test_recommend_falls_back_to_every_node_without_the_index(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(search_index, "fts5_available", lambda: False)
    text = _inventory(render_recommend_prompt(repo, _recommend_session("Shared contracts")))
    assert "**Phases:**" not in text
    for node_id in ("M0", "M0.1", "M0.2", "M0.3", "M1", "M2"):
        assert f"`{node_id}`" in text


def test_similar_node_ids_fuses_queries_and_reports_no_index_as_none(
        repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ranked = search_index.similar_node_ids(
        repo, ["roadmap validator in CI", "validator", "shared contracts"])
    assert ranked is not None and ranked[0] == "M0.2"   # near two of the three queries
    assert "M0.1" in ranked
    assert search_index.similar_node_ids(repo, []) == []
    monkeypatch.setattr(search_index, "fts5_available", lambda: False)
    assert search_index.similar_node_ids(repo, ["validator"]) is None
