"""``policy.strong_review``: a leaf whose touch zones meet a high-risk zone needs one approval from a named set."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from tests.review_repo_helpers import NODE, git, make_review_repo, review_text
from tests.test_orchestrate_plan import ROSTER, only_assignment, plan_repo
from tests.test_review_gate import TWO_FAMILIES

from specy_road import orchestrate_plan as op
from specy_road.bundled_scripts import mark_implementation_reviewed as mir
from specy_road.bundled_scripts import orchestrate_cli, review_cli
from specy_road.orchestration_config import parse_orchestration_text
from specy_road.review_files import reviews_dir
from specy_road.review_gate import evaluate_gate, human_approval_completes
from specy_road.review_strong import applicable_items, zones_meet

#: The leaf's zone is ``src``; ``sonnet`` is the strong reviewer, so opus + sol meet the count but not the item.
STRONG = TWO_FAMILIES.replace(
    "policy: {reviewers_required: 2, reviewers_distinct_families: true}",
    "policy:\n  reviewers_required: 2\n  reviewers_distinct_families: true\n"
    "  strong_review:\n    - {zones: [src/a.py, lib/], require_one_of: [sonnet]}\n")
OUTSIDE = STRONG.replace("[src/a.py, lib/]", "[lib/, specy_road/schemas/]")
WITH_HUMAN = STRONG.replace("require_one_of: [sonnet]", "require_one_of: [sonnet, human]")
UNMET = "strong_review[0] (zones: src/a.py, lib/): the leaf's touch zones meet a strong-review zone; " \
        "need a counting approval from one of sonnet at this commit, have none"


def _review(repo: Path, model: str, **kw) -> None:
    d = reviews_dir(repo, "M1.1")
    d.mkdir(parents=True, exist_ok=True)
    (d / f"REVIEW-{model}.md").write_text(review_text(git(repo, "rev-parse", "HEAD"), model=model, **kw))


def _gate(repo: Path):
    return evaluate_gate(repo, NODE, git(repo, "rev-parse", "HEAD"))


@pytest.mark.parametrize(("a", "b", "prefix", "meet"), [
    ("src", "src/a.py", "", True),                  # a directory prefix of the other, either way
    ("src/a.py", "src/", "", True),
    ("src/*", "src/api/routes.py", "", True),        # a glob zone
    ("src", "srcs/a.py", "", False),
    ("lib", "src/a.py", "", False),
    ("schemas", "sr/schemas/a.json", "sr/", True),   # project-root and git-root forms of one path
    ("sr/schemas", "schemas/", "sr/", True),
])
def test_zones_meet(a: str, b: str, prefix: str, meet: bool) -> None:
    assert zones_meet(a, b, prefix) is meet and zones_meet(b, a, prefix) is meet


def test_applicable_items_lists_only_the_items_a_zone_meets() -> None:
    policy = {"strong_review": [{"zones": ["lib/"], "require_one_of": ["x"]},
                                {"zones": ["src/a.py"], "require_one_of": ["y"]}]}
    assert [i for i, _ in applicable_items(policy, ["src/"])] == [1]
    assert applicable_items(policy, ["docs"]) == [] and applicable_items({}, ["src"]) == []


def test_leaf_inside_a_strong_zone_refuses_without_an_approval_from_the_set(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path, orchestration=STRONG)
    _review(repo, "opus")
    _review(repo, "sol")
    g = _gate(repo)
    assert g.approval_count == 2 and not g.passed   # the count is met; the item is not
    assert UNMET in g.problems()


def test_an_approval_from_the_set_satisfies_the_item(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path, orchestration=STRONG)
    _review(repo, "sonnet")
    _review(repo, "sol")
    g = _gate(repo)
    assert g.passed, g.problems()
    assert g.strong_unmet == []


def test_a_block_from_the_set_does_not_satisfy_the_item(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path, orchestration=STRONG)
    _review(repo, "opus")
    _review(repo, "sol")
    _review(repo, "sonnet", verdict="block", a1="fail")
    assert UNMET in _gate(repo).problems()


def test_an_ineligible_approval_from_the_set_does_not_satisfy_the_item(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path, orchestration=STRONG)
    _review(repo, "opus")
    _review(repo, "sol")
    _review(repo, "sonnet", fresh=False)
    g = _gate(repo)
    assert any(r.path.name == "REVIEW-sonnet.md" for r, _ in g.ineligible)
    assert UNMET in g.problems() and not g.passed


def test_leaf_outside_every_strong_zone_needs_only_the_usual_approvals(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path, orchestration=OUTSIDE)
    _review(repo, "opus")
    _review(repo, "sol")
    assert _gate(repo).passed


def test_policy_on_the_feature_branch_alone_does_not_add_the_item(tmp_path: Path) -> None:
    """Like the rest of the policy, strong_review is read from the integration branch."""
    repo = make_review_repo(tmp_path, orchestration=TWO_FAMILIES)
    (repo / "roadmap" / "orchestration.yaml").write_text(STRONG)
    git(repo, "commit", "-qam", "strong review on the branch only")
    _review(repo, "opus")
    _review(repo, "sol")
    assert _gate(repo).passed


def test_human_completes_only_an_item_that_lists_the_human(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path, orchestration=STRONG)
    _review(repo, "opus")
    assert not human_approval_completes(repo, _gate(repo), NODE)
    repo = make_review_repo(tmp_path / "h", orchestration=WITH_HUMAN)
    _review(repo, "opus")
    assert human_approval_completes(repo, _gate(repo), NODE)


def test_unknown_require_one_of_id_is_a_config_error() -> None:
    _, err = parse_orchestration_text(STRONG.replace("require_one_of: [sonnet]", "require_one_of: [sonnet, nobody]"))
    assert err and "policy/strong_review/0/require_one_of: 'nobody' must be roster entries" in err
    _, err = parse_orchestration_text(STRONG.replace("require_one_of: [sonnet]", "require_one_of: []"))
    assert err and "strong_review" in err


def test_handoff_status_names_the_unmet_item_and_who_satisfies_it(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=STRONG)
    _review(repo, "opus")
    _review(repo, "sol")
    capsys.readouterr()
    with pytest.raises(SystemExit) as e:
        review_cli.main(["handoff", "status", "M1.1", "--json", "--repo-root", str(repo)])
    assert e.value.code == 1
    st = json.loads(capsys.readouterr().out)["nodes"][0]
    assert not st["policy_met"] and UNMET in st["problems"]
    rows = {r["model"]: r for r in st["reviewer_eligibility"]}
    assert rows["sonnet"]["eligible"]   # same family as opus, but its approval is the one the item needs
    assert rows["sonnet"]["reason"].endswith("; would satisfy strong_review[0] (zones: src/a.py, lib/)")
    assert rows["human"]["reason"].endswith("; would not satisfy strong_review[0] (zones: src/a.py, lib/)")


def test_mark_implementation_reviewed_refuses_naming_the_item(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=STRONG)
    (repo / "work").mkdir()
    (repo / "work" / "implementation-summary-M1.1.md").write_text("## Summary\nDid it.\n")
    _review(repo, "opus")
    _review(repo, "sol")
    with pytest.raises(SystemExit) as e:
        mir.main(["--yes", "--repo-root", str(repo)])
    assert e.value.code == 1
    assert UNMET in capsys.readouterr().out


def _strong_roster(require: str, zones: str = "[src]") -> str:
    return ROSTER.replace("policy: {reviewers_required: 2, reviewers_distinct_families: true}",
                          "policy:\n  reviewers_required: 2\n  reviewers_distinct_families: true\n"
                          f"  strong_review:\n    - {{zones: {zones}, require_one_of: {require}}}\n")


def test_plan_shows_the_item_and_picks_a_reviewer_from_the_set(tmp_path: Path) -> None:
    # Without the item the reviewers are sol and opus (test_orchestrate_plan); human is the strong one here.
    repo = plan_repo(tmp_path, roster=_strong_roster("[human]"))
    a = only_assignment(op.build_orchestration_plan(repo, today=date(2026, 11, 1))[0])
    assert a.ok, a.problems
    assert a.strong_review == [{"item": "strong_review[0] (zones: src)", "require_one_of": ["human"],
                                "can_satisfy": ["human"]}]
    assert a.reviewers[0] == "human" and len(a.reviewers) == 2
    assert any(n.endswith("[strong review: strong_review[0] (zones: src)]") for n in a.notes)


def test_plan_leaf_outside_the_zone_has_no_item(tmp_path: Path) -> None:
    repo = plan_repo(tmp_path, roster=_strong_roster("[human]", zones="[lib/]"))
    a = only_assignment(op.build_orchestration_plan(repo, today=date(2026, 11, 1))[0])
    assert a.strong_review == [] and set(a.reviewers) == {"sol", "opus"}


def test_plan_item_no_reviewer_can_satisfy_is_unstaffable(tmp_path: Path, capsys) -> None:
    repo = plan_repo(tmp_path, roster=_strong_roster("[flash]"))   # flash is rostered, but not as a reviewer
    with pytest.raises(SystemExit) as e:
        orchestrate_cli.main(["orchestrate", "plan", "--today", "2026-11-01", "--repo-root", str(repo)])
    assert e.value.code == 1
    out = capsys.readouterr().out
    assert "    strong review strong_review[0] (zones: src): one approval from flash; can satisfy it: none" in out
    assert "! strong_review[0] (zones: src): none of flash can review this leaf" in out


def test_plan_json_carries_the_items(tmp_path: Path, capsys) -> None:
    repo = plan_repo(tmp_path, roster=_strong_roster("[sol, human]"))
    with pytest.raises(SystemExit):
        orchestrate_cli.main(["orchestrate", "plan", "--json", "--today", "2026-11-01", "--repo-root", str(repo)])
    a = json.loads(capsys.readouterr().out)["batches"][0][0]
    assert a["strong_review"][0]["can_satisfy"] == ["sol", "human"]
