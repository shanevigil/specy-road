"""``Review-tally`` trailers on gate commits, and ``policy.quality_routing`` in ``orchestrate plan``."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from tests.review_repo_helpers import NODE, git, make_review_repo, review_text
from tests.test_orchestrate_plan import ROSTER, only_assignment, plan_repo

from specy_road import orchestrate_plan as op
from specy_road.bundled_scripts import mark_implementation_reviewed as mir
from specy_road.review_files import reviews_dir
from specy_road.review_gate import evaluate_gate, write_human_approval
from specy_road.review_tally import leaf_areas, parse_tally, tally_trailers


TALLY = "Review-tally: M1.1 rounds=2 blocks=1 approvals=1 integrity=0 rca=0 findings=boundary:1,correctness:2"


def _gate_repo(tmp_path: Path) -> Path:
    """A review repo on its feature branch with the summary mark-implementation-reviewed reads."""
    repo = make_review_repo(tmp_path)
    (repo / "work").mkdir(exist_ok=True)
    (repo / "work" / "implementation-summary-M1.1.md").write_text("## Summary\nDid it.\n", encoding="utf-8")
    return repo


def _mark_reviewed(repo: Path) -> list[str]:
    """Run the public gate command unattended; the trailer lines of the commit it makes."""
    mir.main(["--yes", "--repo-root", str(repo)])
    return git(repo, "log", "-1", "--format=%B").strip().splitlines()[-2:]


def _two_rounds(repo: Path) -> str:
    """A blocking round on the previous commit, then an approval of HEAD; returns HEAD."""
    head, earlier = git(repo, "rev-parse", "HEAD"), git(repo, "rev-parse", "HEAD~1")
    d = reviews_dir(repo, "M1.1")
    (d / "history").mkdir(parents=True)
    findings = {"correctness": ["x", "y"], "regression": [], "boundary": ["z"], "test_integrity": []}
    (d / "history" / "001.md").write_text(
        review_text(earlier, verdict="block", a1="fail", findings=findings), encoding="utf-8")
    (d / "history" / "002.md").write_text(review_text(head), encoding="utf-8")
    (d / "REVIEW-human.md").write_text(review_text(head), encoding="utf-8")
    return head


def test_tally_trailer_counts_the_leafs_review_records(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    gate = evaluate_gate(repo, NODE, _two_rounds(repo))
    assert gate.passed, gate.problems()
    assert tally_trailers(repo, gate) == [TALLY]
    assert parse_tally(TALLY) == ("M1.1", {"rounds": 2, "blocks": 1, "approvals": 1, "integrity": 0, "rca": 0})


def test_mark_implementation_reviewed_writes_the_tally_after_the_reviewed_by_lines(tmp_path: Path) -> None:
    repo = _gate_repo(tmp_path)
    head = _two_rounds(repo)
    assert _mark_reviewed(repo) == [f"Reviewed-by: human (human) approve {head}", TALLY]


def test_a_human_approval_with_no_history_copy_is_one_round(tmp_path: Path) -> None:
    """write_human_approval files only REVIEW-human.md, as the interactive approval does: the gate counts it, so
    the tally does too."""
    repo = _gate_repo(tmp_path)
    head = git(repo, "rev-parse", "HEAD")
    write_human_approval(repo, NODE, head, None)
    assert not (reviews_dir(repo, "M1.1") / "history").exists()
    assert _mark_reviewed(repo) == [
        f"Reviewed-by: human (human) approve {head}",
        "Review-tally: M1.1 rounds=1 blocks=0 approvals=1 integrity=0 rca=0 findings=none",
    ]


def test_parse_tally_rejects_a_malformed_line() -> None:
    assert parse_tally("Review-tally: M1.1 rounds=x blocks=0 integrity=0 rca=0") is None
    assert parse_tally("Reviewed-by: human (human) approve abc") is None


def test_leaf_areas_take_the_first_components_relative_to_the_project() -> None:
    zones = ["sr/specy_road/a.py", "sr/specy_road/b/", "sr/docs/x.md", " ", "tests/**"]
    assert leaf_areas(zones, 1, "sr/") == ["docs", "specy_road", "tests"]
    assert leaf_areas(zones, 2, "sr/") == ["docs/x.md", "specy_road/a.py", "specy_road/b", "tests/**"]


def _routing_repo(tmp_path: Path, routing: bool) -> Path:
    policy = ("policy:\n  reviewers_required: 2\n  reviewers_distinct_families: true\n"
              f"  quality_routing: {'true' if routing else 'false'}\n"
              "  strong_review:\n    - {zones: [lib/], require_one_of: [human]}\n")
    repo = plan_repo(tmp_path, roster=ROSTER.replace(
        "policy: {reviewers_required: 2, reviewers_distinct_families: true}\n", policy))
    # M1.1 (zone src) landed once before with a blocking round: the src area is flagged.
    with (repo / "roadmap" / "registry.yaml").open("a", encoding="utf-8") as fh:
        fh.write("# gate\n")
    git(repo, "commit", "-qam", "chore(rm-thing): mark implementation reviewed\n\n"
        "Review-tally: M1.1 rounds=2 blocks=1 approvals=1 integrity=0 rca=0 findings=none")
    with (repo / "roadmap" / "registry.yaml").open("a", encoding="utf-8") as fh:
        fh.write("# done\n")
    git(repo, "commit", "-qam", "chore(rm-thing): complete, deregister")
    return repo


def test_quality_routing_off_leaves_the_plan_unchanged(tmp_path: Path) -> None:
    a = only_assignment(op.build_orchestration_plan(_routing_repo(tmp_path, False), today=date(2026, 11, 1))[0])
    assert a.ok and a.strong_review == [] and set(a.reviewers) == {"sol", "opus"}
    assert not any("quality_routing" in n for n in a.notes)


def test_quality_routing_on_routes_a_strong_reviewer_to_a_flagged_area(tmp_path: Path) -> None:
    a = only_assignment(op.build_orchestration_plan(_routing_repo(tmp_path, True), today=date(2026, 11, 1))[0])
    assert a.ok, a.problems
    assert a.strong_review == [{"item": "quality_routing (area: src)", "require_one_of": ["human"],
                                "can_satisfy": ["human"]}]
    assert a.reviewers[0] == "human"
    assert any(n.endswith("[strong review: quality_routing (area: src)]") for n in a.notes)
