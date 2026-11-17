"""Promoting accepted ideas into the roadmap graph.

Promotion is the only part of brainstorming that writes to the graph, so the
things worth pinning are that it produces nodes indistinguishable from
hand-authored ones, that it leaves the graph valid, and that it refuses rather
than half-applies.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from specy_road.brainstorm_promote import (
    pending_ideas,
    promote_session,
)
from specy_road.brainstorm_session import (
    BrainstormError,
    BrainstormSession,
    add_idea,
    read_session,
)
from specy_road.roadmap_load import load_roadmap
from tests.helpers import DOGFOOD
from tests.support.same.by_id_a6a5bf211114 import by_id
import subprocess
from specy_road.brainstorm_promote import PROMOTE_CODENAME_MAX_WORDS
from specy_road.brainstorm_session import write_session
from specy_road.bundled_scripts.roadmap_crud_prepare import next_sibling_order
from specy_road.roadmap_layout import ordered_tree_rows
from tests.support.same.cli_3c7fcb2cc75e import cli


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    """A real, valid graph — the dogfood fixture, copied out of the checkout."""
    dest = tmp_path / "repo"
    shutil.copytree(DOGFOOD, dest)
    return dest


def _accepted_session(**kw) -> BrainstormSession:
    s = BrainstormSession(slug="payments", topic="Expand payments", **kw)
    idea = add_idea(
        s,
        title="Stored payment vault",
        rationale="Cuts PCI scope",
        effort="M",
        evidence=["https://example.com/a"],
    )
    idea.status = "accepted"
    return s




def test_an_accepted_idea_becomes_a_node_under_the_anchor(repo: Path) -> None:
    s = _accepted_session(under="M1")

    results = promote_session(repo, s)

    assert len(results) == 1
    node = by_id(repo)[results[0].node_id]
    assert node["parent_id"] == "M1"
    assert node["title"] == "Stored payment vault"
    assert node["type"] == "milestone"
    assert node["status"] == "Not Started"


def test_the_graph_still_validates_after_promotion(repo: Path) -> None:
    """promote_session runs validation itself and raises if it broke anything."""
    s = _accepted_session(under="M1")
    add_idea(s, title="Second idea").status = "accepted"

    assert len(promote_session(repo, s)) == 2


def test_each_promoted_idea_gets_its_own_id(repo: Path) -> None:
    s = _accepted_session(under="M1")
    add_idea(s, title="Second idea").status = "accepted"
    add_idea(s, title="Third idea").status = "accepted"

    ids = [r.node_id for r in promote_session(repo, s)]

    assert len(set(ids)) == 3


def test_the_idea_records_the_node_it_became(repo: Path) -> None:
    s = _accepted_session(under="M1")

    result = promote_session(repo, s)[0]

    assert s.ideas[0].promoted_node_key == result.node_key
    assert by_id(repo)[result.node_id]["node_key"] == result.node_key


def test_promotion_happens_once(repo: Path) -> None:
    s = _accepted_session(under="M1")
    promote_session(repo, s)

    assert pending_ideas(s) == []
    assert promote_session(repo, s) == []


def test_a_failure_mid_batch_does_not_duplicate_on_the_next_run(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The batch cannot be one transaction, so it has to be resumable.

    Chunk routing reads what the previous write left on disk, so each node is
    its own commit. If the session were only saved once the whole batch
    succeeded, a failure part-way would leave nodes on the graph that no idea
    claimed — and re-running would promote them a second time.
    """
    import specy_road.brainstorm_promote as mod

    s = _accepted_session(under="M1")
    add_idea(s, title="Second idea").status = "accepted"
    add_idea(s, title="Third idea").status = "accepted"

    real = mod.append_node_to_chunk
    calls = {"n": 0}

    def _fail_on_third(*a, **k):
        calls["n"] += 1
        if calls["n"] == 3:
            raise RuntimeError("chunk write blew up")
        return real(*a, **k)

    monkeypatch.setattr(mod, "append_node_to_chunk", _fail_on_third)
    with pytest.raises(RuntimeError):
        promote_session(repo, s)

    # The two that landed are recorded, on disk, as already promoted.
    reloaded = read_session(repo, s.slug)
    done = [i for i in reloaded.ideas if i.promoted_node_key]
    assert len(done) == 2

    monkeypatch.undo()
    again = promote_session(repo, reloaded)

    assert [r.title for r in again] == ["Third idea"]
    titles = [n["title"] for n in by_id(repo).values()]
    for t in ("Second idea", "Third idea"):
        assert titles.count(t) == 1


def test_the_planning_sheet_is_seeded_from_the_idea(repo: Path) -> None:
    s = _accepted_session(under="M1")

    node_id = promote_session(repo, s)[0].node_id

    sheet = next((repo / "planning").glob(f"{node_id}_*.md"))
    text = sheet.read_text(encoding="utf-8")
    assert "Cuts PCI scope" in text
    assert "Initial sizing at brainstorm time: M." in text
    assert "Promoted from brainstorm idea `B1`" in text
    assert "https://example.com/a" in text


def test_the_seeded_sheet_keeps_the_template_sections(repo: Path) -> None:
    """Seeding is a section swap, not a rewrite; validate reads the rest."""
    s = _accepted_session(under="M1")

    node_id = promote_session(repo, s)[0].node_id

    sheet = next((repo / "planning").glob(f"{node_id}_*.md"))
    text = sheet.read_text(encoding="utf-8")
    for heading in ("## Intent", "## Approach", "## Tasks / checklist", "## References"):
        assert heading in text


def test_only_accepted_ideas_are_promoted(repo: Path) -> None:
    s = _accepted_session(under="M1")
    add_idea(s, title="Rejected one").status = "rejected"
    add_idea(s, title="Untriaged one")

    results = promote_session(repo, s)

    assert [r.idea_id for r in results] == ["B1"]


def test_a_dry_run_writes_nothing(repo: Path) -> None:
    s = _accepted_session(under="M1")
    before = set(by_id(repo))

    results = promote_session(repo, s, dry_run=True)

    assert len(results) == 1
    assert set(by_id(repo)) == before
    assert s.ideas[0].promoted_node_key is None


def test_a_dry_run_still_allocates_distinct_ids(repo: Path) -> None:
    s = _accepted_session(under="M1")
    add_idea(s, title="Second idea").status = "accepted"

    ids = [r.node_id for r in promote_session(repo, s, dry_run=True)]

    assert len(set(ids)) == 2


def test_an_unknown_anchor_promotes_nothing(repo: Path) -> None:
    s = _accepted_session(under="M404")
    before = set(by_id(repo))

    with pytest.raises(BrainstormError, match="M404"):
        promote_session(repo, s)

    assert set(by_id(repo)) == before
    assert s.ideas[0].promoted_node_key is None


def test_gates_are_not_a_promotion_target(repo: Path) -> None:
    """A gate is a human hold, not work, so an idea never becomes one."""
    s = _accepted_session(under="M1")

    with pytest.raises(BrainstormError, match="--type"):
        promote_session(repo, s, node_type="gate")


def test_under_overrides_the_session_anchor(repo: Path) -> None:
    s = _accepted_session(under="M1")

    result = promote_session(repo, s, under="M0")[0]

    assert by_id(repo)[result.node_id]["parent_id"] == "M0"


def test_promoting_to_the_root_makes_a_top_level_node(repo: Path) -> None:
    s = _accepted_session()

    result = promote_session(repo, s, node_type="phase")[0]

    node = by_id(repo)[result.node_id]
    assert node.get("parent_id") is None
    assert "execution_milestone" not in node


def test_promoted_nodes_inherit_the_anchor_execution_milestone(repo: Path) -> None:
    s = _accepted_session(under="M1")

    node_id = promote_session(repo, s)[0].node_id

    assert by_id(repo)[node_id]["execution_milestone"] == "Agentic-led"


def test_promoted_nodes_inherit_human_led_from_the_anchor(repo: Path) -> None:
    s = _accepted_session(under="M0")

    node_id = promote_session(repo, s)[0].node_id

    assert by_id(repo)[node_id]["execution_milestone"] == "Human-led"


def test_promoted_nodes_accept_execution_milestone_override(repo: Path) -> None:
    s = _accepted_session(under="M1")

    node_id = promote_session(repo, s, execution_milestone="Human-led")[0].node_id

    assert by_id(repo)[node_id]["execution_milestone"] == "Human-led"


def test_promoted_nodes_omit_execution_milestone_when_the_anchor_has_none(
    repo: Path,
) -> None:
    s = _accepted_session(under="M0.3")

    node_id = promote_session(repo, s)[0].node_id

    assert "execution_milestone" not in by_id(repo)[node_id]









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

    assert by_id(repo)[node_id]["codename"] == "-".join(words[:PROMOTE_CODENAME_MAX_WORDS])



def test_promote_caps_codename_when_the_title_starts_with_punctuation(repo: Path) -> None:
    s = BrainstormSession(slug="pay", topic="t", under="M1")
    idea = add_idea(s, title="!!! ??? ... --- Five Six Seven Eight Nine Ten")
    idea.status = "accepted"

    node_id = promote_session(repo, s)[0].node_id

    assert by_id(repo)[node_id]["codename"] == "five-six-seven-eight"



def test_revise_codename_on_the_idea_wins_over_title_derivation(repo: Path) -> None:
    s = BrainstormSession(slug="pay", topic="t", under="M1")
    idea = add_idea(s, title="Some Long Title That Would Slug Longer")
    idea.codename = "pm-picked-slug"
    idea.status = "accepted"

    node_id = promote_session(repo, s)[0].node_id

    assert by_id(repo)[node_id]["codename"] == "pm-picked-slug"



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
    nodes = by_id(repo)
    second_id = next(r.node_id for r in results if r.title == "Second")
    first_id = next(r.node_id for r in results if r.title == "First")
    assert nodes[second_id]["sibling_order"] == base
    assert nodes[first_id]["sibling_order"] == base + 1
    assert nodes[first_id]["goal"] == "Latency drops because we cache"



def test_cli_accept_without_reason_preserves_accept_order(repo: Path) -> None:
    slug = "how-do-we-expand-payments"
    assert cli(repo, "start", "--topic", "How do we expand payments?", "--under", "M1")[0] == 0
    assert cli(repo, "add-idea", "--title", "Created first")[0] == 0
    assert cli(repo, "add-idea", "--title", "Created second")[0] == 0
    assert cli(repo, "accept", "B2")[0] == 0
    assert cli(repo, "accept", "B1")[0] == 0
    session = read_session(repo, slug)
    assert [i.id for i in session.ideas] == ["B1", "B2"]
    assert int(session.by_id("B2").decision["seq"]) < int(session.by_id("B1").decision["seq"])

    results = promote_session(repo, session)
    nodes = by_id(repo)
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
    last_order = max(by_id(repo)[r.node_id]["sibling_order"] for r in first)

    three = add_idea(s, title="Batch two last")
    three.status = "accepted"
    three.decision = {"status": "accepted", "seq": "3"}
    second = promote_session(repo, s)
    assert len(second) == 1
    assert by_id(repo)[second[0].node_id]["sibling_order"] == last_order + 1
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
