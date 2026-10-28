"""Tests for the review gate: which review records count, and when policy is met."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from tests.review_repo_helpers import NODE, commit_file, git, make_review_repo, review_text

from specy_road.review_files import reviews_dir
from specy_road.review_gate import evaluate_gate

TWO_FAMILIES = """version: 1
roster:
  - {id: human, family: human, roles: [reviewer]}
  - {id: opus, family: anthropic, roles: [reviewer]}
  - {id: sonnet, family: anthropic, roles: [reviewer]}
  - {id: sol, family: openai, roles: [reviewer]}
  - {id: composer, family: cursor, roles: [executor]}
  - {id: astra, family: openai, roles: [executor]}
policy: {reviewers_required: 2, reviewers_distinct_families: true}
substitutions:
  - {slot: reviewer-openai, use: astra, scope: [M1.1], decided: 2026-01-01, expires: 2026-12-31}
"""


def _review(repo: Path, model: str, **kw) -> None:
    d = reviews_dir(repo, "M1.1")
    d.mkdir(parents=True, exist_ok=True)
    commit = kw.pop("commit", None) or git(repo, "rev-parse", "HEAD")
    (d / f"REVIEW-{model}.md").write_text(review_text(commit, model=model, **kw))


def _gate(repo: Path, today: date | None = None):
    return evaluate_gate(repo, NODE, git(repo, "rev-parse", "HEAD"), today=today)


def test_no_reviews_fails_default_policy(tmp_path: Path) -> None:
    g = _gate(make_review_repo(tmp_path))
    assert not g.passed
    assert g.required == 1 and not g.distinct_families
    assert "need 1 approvals at this commit, have 0" in g.problems()


def test_one_human_approval_passes_default_policy(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    _review(repo, "human")
    assert _gate(repo).passed


def test_unrostered_model_does_not_count_under_default_roster(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    _review(repo, "opus")
    g = _gate(repo)
    assert not g.passed
    assert "not a rostered reviewer" in g.ineligible[0][1]


def test_a_new_commit_makes_reviews_stale(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    _review(repo, "human")
    commit_file(repo, "src/b.py", "x\n", "fix")
    g = _gate(repo)
    assert not g.passed
    assert len(g.stale) == 1
    assert "re-review" in " ".join(g.problems())


def test_block_at_head_fails_even_with_enough_approvals(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path, orchestration=TWO_FAMILIES)
    _review(repo, "opus")
    _review(repo, "sol")
    _review(repo, "human", verdict="block", a1="fail")
    g = _gate(repo)
    assert g.approval_count == 2
    assert not g.passed
    assert "human blocks this commit" in " ".join(g.problems())


def test_distinct_families_counts_a_family_once(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path, orchestration=TWO_FAMILIES)
    _review(repo, "opus")
    _review(repo, "sonnet")
    g = _gate(repo)
    assert len(g.approvals) == 2 and g.approval_count == 1
    assert not g.passed
    _review(repo, "sol")
    assert _gate(repo).passed


def test_executor_only_roster_entry_cannot_review(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path, orchestration=TWO_FAMILIES)
    _review(repo, "composer")
    assert _gate(repo).ineligible


def test_substitute_counts_until_it_expires(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path, orchestration=TWO_FAMILIES)
    _review(repo, "opus")
    d = reviews_dir(repo, "M1.1")
    (d / "REVIEW-astra.md").write_text(review_text(git(repo, "rev-parse", "HEAD"), model="astra"))
    assert _gate(repo, today=date(2026, 6, 1)).passed
    expired = _gate(repo, today=date(2027, 1, 1))
    assert not expired.passed
    assert "no active substitution" in expired.ineligible[0][1]


def test_fresh_session_required_by_default(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    _review(repo, "human", fresh=False)
    g = _gate(repo)
    assert not g.passed and "fresh" in g.ineligible[0][1]


def test_invalid_record_is_reported(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    d = reviews_dir(repo, "M1.1")
    d.mkdir(parents=True)
    text = review_text(git(repo, "rev-parse", "HEAD")).replace("  A2: pass\n", "")
    (d / "REVIEW-human.md").write_text(text)
    g = _gate(repo)
    assert not g.passed
    assert "no result for A2" in g.problems()[0]


def test_broken_orchestration_config_fails_closed(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path, orchestration="version: 1\npolicy: {reviewers_required: 0}\n")
    _review(repo, "human")
    g = _gate(repo)
    assert not g.passed
    assert g.config_error
