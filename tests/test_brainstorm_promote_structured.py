"""M4.2: target parents, --by-cluster, --min-recommendation and --plan on promote."""

from __future__ import annotations

import contextlib
import io
import shutil
from pathlib import Path

import pytest

from specy_road.bundled_scripts import brainstorm_cli
from specy_road.bundled_scripts.brainstorm_promote import pending_ideas, promote_session
from specy_road.bundled_scripts.brainstorm_session import (
    BrainstormError,
    BrainstormSession,
    add_idea,
    read_session,
    write_session,
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


def _cli(repo: Path, *args: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            brainstorm_cli.main(["brainstorm", *args, "--repo-root", str(repo)])
            code = 0
        except SystemExit as e:
            code = int(e.code) if isinstance(e.code, int) else 1
    return code, out.getvalue(), err.getvalue()


def _session(*ideas: dict) -> BrainstormSession:
    """Accepted ideas, in order, anchored under M1."""
    s = BrainstormSession(slug="pay", topic="Expand payments", under="M1", mode="roadmap")
    for fields in ideas:
        idea = add_idea(s, title=fields.pop("title"), rationale="r")
        idea.status = "accepted"
        for key, value in fields.items():
            setattr(idea, key, value)
    return s


def _sheet(root: Path, node_id: str) -> str:
    return (root / _by_id(root)[node_id]["planning_dir"]).read_text(encoding="utf-8")


# A1 — target parent


def test_revise_target_parent_is_stored_and_cleared(repo: Path) -> None:
    write_session(repo, _session({"title": "Vault"}))

    assert _cli(repo, "revise", "B1", "--target-parent", "M0")[0] == 0
    assert read_session(repo, "pay").by_id("B1").target_parent == "M0"
    assert "target_parent: M0" in (repo / "work" / "brainstorm-pay.yaml").read_text(encoding="utf-8")

    assert _cli(repo, "revise", "B1", "--target-parent", "")[0] == 0
    idea = read_session(repo, "pay").by_id("B1")
    assert idea.target_parent is None
    assert idea.status == "accepted"


def test_promote_honours_target_parent_and_falls_back_to_under(repo: Path) -> None:
    s = _session({"title": "Vault", "target_parent": "M0"}, {"title": "Refunds"})

    results = promote_session(repo, s, under="M2")

    assert [(r.title, r.parent_id) for r in results] == [("Vault", "M0"), ("Refunds", "M2")]
    nodes = _by_id(repo)
    assert nodes[results[0].node_id]["parent_id"] == "M0"
    assert nodes[results[1].node_id]["parent_id"] == "M2"


def test_unknown_target_parent_is_refused_before_anything_is_written(repo: Path) -> None:
    before = len(load_roadmap(repo)["nodes"])
    s = _session({"title": "Refunds"}, {"title": "Vault", "target_parent": "M9"})

    with pytest.raises(BrainstormError, match="M9"):
        promote_session(repo, s)

    assert len(load_roadmap(repo)["nodes"]) == before
    assert len(pending_ideas(s)) == 2


# A2 — one node per cluster lead


def test_by_cluster_promotes_the_lead_and_lists_the_others_as_alternatives(repo: Path) -> None:
    s = _session(
        {"title": "Card vault", "cluster_id": "c1", "recommendation": "consider"},
        {"title": "Token service", "cluster_id": "c1", "recommendation": "strong"},
        {"title": "Refunds"},
    )

    results = promote_session(repo, s, by_cluster=True)

    assert [(r.idea_id, r.linked) for r in results] == [("B2", ("B1",)), ("B3", ())]
    lead = results[0]
    assert s.by_id("B1").promoted_node_key == lead.node_key == s.by_id("B2").promoted_node_key
    assert pending_ideas(s) == []
    assert "- Alternative considered: B1 Card vault (accepted)" in _sheet(repo, lead.node_id)
    titles = [n["title"] for n in load_roadmap(repo)["nodes"]]
    assert "Card vault" not in titles and "Token service" in titles


def test_by_cluster_ties_go_to_the_earlier_accept(repo: Path) -> None:
    s = _session({"title": "First", "cluster_id": "c1"}, {"title": "Second", "cluster_id": "c1"})

    results = promote_session(repo, s, by_cluster=True, dry_run=True)

    assert [(r.idea_id, r.linked) for r in results] == [("B1", ("B2",))]


# A3 — minimum recommendation


def test_min_recommendation_strong_skips_weaker_verdicts(repo: Path) -> None:
    s = _session(
        {"title": "Vault", "recommendation": "strong"},
        {"title": "Refunds", "recommendation": "consider"},
        {"title": "Wallets"},
    )

    results = promote_session(repo, s, min_recommendation="strong")

    assert [r.idea_id for r in results] == ["B1"]
    assert [i.id for i in pending_ideas(s)] == ["B2", "B3"]


def test_cli_min_recommendation_reports_what_it_skipped(repo: Path) -> None:
    write_session(repo, _session({"title": "Vault", "recommendation": "consider"},
                                 {"title": "Refunds", "recommendation": "park"}))

    code, out, err = _cli(repo, "promote", "--min-recommendation", "consider")

    assert code == 0
    assert "(from B1)" in out and "Refunds" not in out
    assert "skipped B2 (park): below --min-recommendation consider" in err
    assert [i.id for i in pending_ideas(read_session(repo, "pay"))] == ["B2"]


# A4 — plan file

PLAN = """\
nodes:
  - ref: payments
    parent: M1
    type: phase
    title: Payments platform
  - ref: vault
    parent: payments
    type: task
    title: Card vault
    acceptance: [Cards are tokenised, No PAN in logs]
    dependencies: [token, M0.1]
    ideas: [B1, B3]
  - ref: token
    parent: payments
    type: task
    title: Token service
    ideas: [B2]
"""


def test_plan_creates_the_tree_and_links_ideas_by_id(repo: Path) -> None:
    s = _session({"title": "Vault idea"}, {"title": "Token idea"}, {"title": "PAN scrubbing"})
    plan = repo / "plan.yaml"
    plan.write_text(PLAN, encoding="utf-8")

    results = promote_session(repo, s, plan=plan)

    nodes = _by_id(repo)
    phase, vault, token = (nodes[r.node_id] for r in results)
    assert (phase["type"], phase["parent_id"]) == ("phase", "M1")
    assert vault["parent_id"] == token["parent_id"] == phase["id"]
    assert vault["acceptance"] == ["Cards are tokenised", "No PAN in logs"]
    assert vault["dependencies"] == [token["node_key"], nodes["M0.1"]["node_key"]]
    assert (s.by_id("B1").promoted_node_key, s.by_id("B3").promoted_node_key) == (vault["node_key"],) * 2
    assert s.by_id("B2").promoted_node_key == token["node_key"]
    assert [r.idea_id for r in results] == ["", "B1", "B2"]
    assert "- Also promoted into this node: brainstorm idea B3 PAN scrubbing" in _sheet(repo, vault["id"])


def test_cli_plan_runs_with_no_pending_ideas(repo: Path) -> None:
    write_session(repo, BrainstormSession(slug="pay", topic="t", under="M1", mode="roadmap"))
    plan = repo / "plan.yaml"
    plan.write_text("nodes:\n  - title: Payments platform\n    type: phase\n", encoding="utf-8")

    code, out, _err = _cli(repo, "promote", "--plan", str(plan))

    assert code == 0, out
    assert "under M1 — Payments platform  (plan)" in out
    assert any(n["title"] == "Payments platform" for n in load_roadmap(repo)["nodes"])


def test_plan_dry_run_nests_ids_and_writes_nothing(repo: Path) -> None:
    s = _session({"title": "Vault idea"}, {"title": "Token idea"}, {"title": "PAN scrubbing"})
    plan = repo / "plan.yaml"
    plan.write_text(PLAN, encoding="utf-8")
    before = load_roadmap(repo)["nodes"]

    results = promote_session(repo, s, plan=plan, dry_run=True)

    assert [r.parent_id for r in results] == ["M1", results[0].node_id, results[0].node_id]
    assert results[2].node_id == f"{results[0].node_id}.2"
    assert load_roadmap(repo)["nodes"] == before
    assert len(pending_ideas(s)) == 3


@pytest.mark.parametrize(("body", "match"), [
    ("nodes:\n  - {title: A, parent: later}\n  - {ref: later, title: B}\n", "neither an earlier plan ref"),
    ("nodes:\n  - {title: A, owner: me}\n", "unknown key"),
    ("nodes:\n  - {parent: M1}\n", "`title` is required"),
    ("nodes:\n  - {title: A, ideas: [B2]}\n", "B2 is not an accepted"),
    ("nodes:\n  - {title: A, ideas: [B1]}\n  - {title: B, ideas: [B1]}\n", "linked by an earlier"),
    ("nodes:\n  - {title: A, dependencies: [nope]}\n", "'nope'"),
    ("nodes:\n  - {title: A, type: gate}\n", "'gate' not one of"),
    ("nodes:\n  - {ref: M0, title: A}\n", "already a plan ref or a roadmap node id"),
    ("nodes: []\n", "non-empty `nodes:`"),
])
def test_a_bad_plan_is_refused_before_anything_is_written(repo: Path, body: str, match: str) -> None:
    s = _session({"title": "Vault"})
    add_idea(s, title="Proposed only")
    plan = repo / "plan.yaml"
    plan.write_text(body, encoding="utf-8")
    before = load_roadmap(repo)["nodes"]

    with pytest.raises(BrainstormError, match=match):
        promote_session(repo, s, plan=plan)

    assert load_roadmap(repo)["nodes"] == before


def test_plan_does_not_combine_with_cluster_or_recommendation_filters(repo: Path) -> None:
    plan = repo / "plan.yaml"
    plan.write_text("nodes:\n  - {title: A}\n", encoding="utf-8")

    with pytest.raises(BrainstormError, match="--plan places every node itself"):
        promote_session(repo, _session({"title": "Vault"}), plan=plan, by_cluster=True)
