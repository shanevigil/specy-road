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

from specy_road.bundled_scripts.brainstorm_promote import (
    pending_ideas,
    promote_session,
)
from specy_road.bundled_scripts.brainstorm_session import (
    BrainstormError,
    BrainstormSession,
    add_idea,
    read_session,
)
from specy_road.bundled_scripts.roadmap_load import load_roadmap
from tests.helpers import DOGFOOD


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


def _by_id(root: Path) -> dict[str, dict]:
    return {n["id"]: n for n in load_roadmap(root)["nodes"]}


def test_an_accepted_idea_becomes_a_node_under_the_anchor(repo: Path) -> None:
    s = _accepted_session(under="M1")

    results = promote_session(repo, s)

    assert len(results) == 1
    node = _by_id(repo)[results[0].node_id]
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
    assert _by_id(repo)[result.node_id]["node_key"] == result.node_key


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
    import specy_road.bundled_scripts.brainstorm_promote as mod

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
    titles = [n["title"] for n in _by_id(repo).values()]
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
    before = set(_by_id(repo))

    results = promote_session(repo, s, dry_run=True)

    assert len(results) == 1
    assert set(_by_id(repo)) == before
    assert s.ideas[0].promoted_node_key is None


def test_a_dry_run_still_allocates_distinct_ids(repo: Path) -> None:
    s = _accepted_session(under="M1")
    add_idea(s, title="Second idea").status = "accepted"

    ids = [r.node_id for r in promote_session(repo, s, dry_run=True)]

    assert len(set(ids)) == 2


def test_an_unknown_anchor_promotes_nothing(repo: Path) -> None:
    s = _accepted_session(under="M404")
    before = set(_by_id(repo))

    with pytest.raises(BrainstormError, match="M404"):
        promote_session(repo, s)

    assert set(_by_id(repo)) == before
    assert s.ideas[0].promoted_node_key is None


def test_gates_are_not_a_promotion_target(repo: Path) -> None:
    """A gate is a human hold, not work, so an idea never becomes one."""
    s = _accepted_session(under="M1")

    with pytest.raises(BrainstormError, match="--type"):
        promote_session(repo, s, node_type="gate")


def test_under_overrides_the_session_anchor(repo: Path) -> None:
    s = _accepted_session(under="M1")

    result = promote_session(repo, s, under="M0")[0]

    assert _by_id(repo)[result.node_id]["parent_id"] == "M0"


def test_promoting_to_the_root_makes_a_top_level_node(repo: Path) -> None:
    s = _accepted_session()

    result = promote_session(repo, s, node_type="phase")[0]

    assert _by_id(repo)[result.node_id].get("parent_id") is None
