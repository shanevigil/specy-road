"""M3.7: promote validates once, capped codenames, goal, order, missing-field list."""

from __future__ import annotations

import contextlib
import io
import shutil
import subprocess
from pathlib import Path

import pytest

from specy_road.bundled_scripts import brainstorm_cli
from specy_road.bundled_scripts.brainstorm_promote import (
    PROMOTE_CODENAME_MAX_WORDS,
    pending_ideas,
    promote_session,
)
from specy_road.bundled_scripts.brainstorm_session import (
    BrainstormSession,
    add_idea,
    read_session,
    write_session,
)
from specy_road.bundled_scripts.roadmap_crud_prepare import next_sibling_order
from specy_road.bundled_scripts.roadmap_layout import ordered_tree_rows
from specy_road.bundled_scripts.roadmap_load import load_roadmap
from tests.helpers import DOGFOOD


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    dest = tmp_path / "repo"
    shutil.copytree(DOGFOOD, dest)
    return dest


def _by_id(root: Path) -> dict[str, dict]:
    return {n["id"]: n for n in load_roadmap(root)["nodes"]}


def _cli(repo: Path, *args: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            brainstorm_cli.main(["brainstorm", *args, "--repo-root", str(repo)])
            code = 0
        except SystemExit as e:
            code = int(e.code) if isinstance(e.code, int) else 1
    return code, out.getvalue(), err.getvalue()


def test_promote_prints_pin_warnings_once_for_a_multi_node_batch(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    (repo / "requirements.txt").write_text("specy-road==0.0.1\n", encoding="utf-8")
    s = BrainstormSession(slug="pay", topic="t", under="M1")
    for title in ("One", "Two", "Three"):
        add_idea(s, title=title).status = "accepted"

    promote_session(repo, s)

    err = capsys.readouterr().err
    assert err.count("pins specy-road") == 1
    assert "pins specy-road 0.0.1" in err


def test_promote_derives_codename_from_the_first_four_title_words(repo: Path) -> None:
    s = BrainstormSession(slug="pay", topic="t", under="M1")
    words = [f"word{i}" for i in range(PROMOTE_CODENAME_MAX_WORDS + 3)]
    idea = add_idea(s, title=" ".join(words))
    idea.status = "accepted"

    node_id = promote_session(repo, s)[0].node_id

    assert _by_id(repo)[node_id]["codename"] == "-".join(words[:PROMOTE_CODENAME_MAX_WORDS])


def test_promote_caps_codename_when_the_title_starts_with_punctuation(repo: Path) -> None:
    s = BrainstormSession(slug="pay", topic="t", under="M1")
    idea = add_idea(s, title="!!! ??? ... --- Five Six Seven Eight Nine Ten")
    idea.status = "accepted"

    node_id = promote_session(repo, s)[0].node_id

    assert _by_id(repo)[node_id]["codename"] == "five-six-seven-eight"


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

    base = next_sibling_order(repo, "M1", None)
    results = promote_session(repo, s)

    assert len(results) == 2
    nodes = _by_id(repo)
    second_id = next(r.node_id for r in results if r.title == "Second")
    first_id = next(r.node_id for r in results if r.title == "First")
    assert nodes[second_id]["sibling_order"] == base
    assert nodes[first_id]["sibling_order"] == base + 1
    assert nodes[first_id]["goal"] == "Latency drops because we cache"


def test_cli_accept_without_reason_preserves_accept_order(repo: Path) -> None:
    slug = "how-do-we-expand-payments"
    assert _cli(repo, "start", "--topic", "How do we expand payments?", "--under", "M1")[0] == 0
    assert _cli(repo, "add-idea", "--title", "Created first")[0] == 0
    assert _cli(repo, "add-idea", "--title", "Created second")[0] == 0
    assert _cli(repo, "accept", "B2")[0] == 0
    assert _cli(repo, "accept", "B1")[0] == 0
    session = read_session(repo, slug)
    assert [i.id for i in session.ideas] == ["B1", "B2"]
    assert int(session.by_id("B2").decision["seq"]) < int(session.by_id("B1").decision["seq"])

    results = promote_session(repo, session)
    nodes = _by_id(repo)
    b2 = next(r.node_id for r in results if r.idea_id == "B2")
    b1 = next(r.node_id for r in results if r.idea_id == "B1")
    assert nodes[b2]["sibling_order"] < nodes[b1]["sibling_order"]


def test_successive_promote_appends_after_existing_siblings(repo: Path) -> None:
    s = BrainstormSession(slug="pay", topic="t", under="M1")
    one = add_idea(s, title="Batch one first")
    one.status = "accepted"
    one.decision = {"status": "accepted", "seq": "1"}
    two = add_idea(s, title="Batch one second")
    two.status = "accepted"
    two.decision = {"status": "accepted", "seq": "2"}
    first = promote_session(repo, s)
    last_order = max(_by_id(repo)[r.node_id]["sibling_order"] for r in first)

    three = add_idea(s, title="Batch two last")
    three.status = "accepted"
    three.decision = {"status": "accepted", "seq": "3"}
    second = promote_session(repo, s)
    assert len(second) == 1
    assert _by_id(repo)[second[0].node_id]["sibling_order"] == last_order + 1
    under_m1 = [
        (n["title"], n.get("sibling_order"))
        for n, _depth in ordered_tree_rows(load_roadmap(repo)["nodes"])
        if n.get("parent_id") == "M1" and n["title"] in (
            "Batch one first", "Batch one second", "Batch two last",
        )
    ]
    assert [t for t, _o in under_m1] == [
        "Batch one first", "Batch one second", "Batch two last",
    ]


def test_promote_rolls_back_when_deferred_validate_rejects_a_duplicate_title(
    repo: Path,
) -> None:
    """A title that already exists on the graph must not leave a node or marker."""
    s = BrainstormSession(slug="pay", topic="t", under="M1")
    add_idea(s, title="Implementation track").status = "accepted"
    write_session(repo, s)
    before = load_roadmap(repo)["nodes"]
    n_before = len(before)
    titles_before = [n["title"] for n in before]

    with pytest.raises(ValueError, match="duplicate title"):
        promote_session(repo, s)

    after = load_roadmap(repo)["nodes"]
    assert len(after) == n_before
    assert [n["title"] for n in after].count("Implementation track") == 1
    assert titles_before == [n["title"] for n in after]
    reloaded = read_session(repo, s.slug)
    assert reloaded.ideas[0].promoted_node_key is None
    assert [i.title for i in pending_ideas(reloaded)] == ["Implementation track"]

    with pytest.raises(ValueError, match="duplicate title"):
        promote_session(repo, reloaded)
    assert len(load_roadmap(repo)["nodes"]) == n_before
    assert pending_ideas(read_session(repo, s.slug))


def test_promote_lists_nodes_still_missing_acceptance_or_touch_zones(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    s = BrainstormSession(slug="pay", topic="t", under="M1")
    add_idea(s, title="Needs authoring").status = "accepted"

    results = promote_session(repo, s)

    err = capsys.readouterr().err
    assert "still missing acceptance or touch_zones" in err
    assert results[0].node_id in err
