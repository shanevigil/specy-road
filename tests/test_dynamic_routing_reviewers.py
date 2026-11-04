"""M11.33: a reviewer whose harness routes models dynamically does not count as an independent family by default."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.review_repo_helpers import NODE, git, make_review_repo, review_text

from specy_road.review_eligible import reviewer_eligibility
from specy_road.review_files import reviews_dir
from specy_road.review_gate import evaluate_gate


def _roster(rev: str, *, distinct: bool = True) -> str:
    return ("version: 1\nroster:\n  - {id: opus, family: anthropic, roles: [reviewer]}\n"
            f"  - {{id: rev, family: openai, roles: [reviewer]{rev}}}\n"
            f"policy: {{reviewers_required: 2, reviewers_distinct_families: {str(distinct).lower()}}}\n")


def _gate(tmp_path: Path, rev: str, *, distinct: bool = True, rev_verdict: str = "approve"):
    repo = make_review_repo(tmp_path, orchestration=_roster(rev, distinct=distinct))
    head = git(repo, "rev-parse", "HEAD")
    d = reviews_dir(repo, "M1.1")
    d.mkdir(parents=True)
    (d / "REVIEW-opus.md").write_text(review_text(head, model="opus"))
    (d / "REVIEW-rev.md").write_text(review_text(head, model="rev", verdict=rev_verdict,
                                                 a1="pass" if rev_verdict == "approve" else "fail"))
    return repo, evaluate_gate(repo, NODE, head)


@pytest.mark.parametrize("rev, counts", [
    ("", True),                                                   # routing absent: fixed
    (", routing: fixed", True),
    (", routing: dynamic", False),
    (", routing: dynamic, pinned: true", True),
    (", harness: cursor", False),                                 # A4: no harness_model, no profile: no --model
    (", harness: cursor, harness_model: auto", False),            # A4: Cursor's Auto
    (", harness: cursor, channels: {cli: 'agent -p {prompt}'}", False),
    (""", harness: cursor, channels: {cli: "agent -p --model gpt-5.6-sol '{prompt}"}""", False),   # unbalanced quote
    (", harness: cursor, harness_model: gpt-5.6-sol-high", True),
    (", harness: cursor, pinned: true", True),
])
def test_dynamic_routing_approval_does_not_count_toward_distinct_families(tmp_path: Path, rev: str, counts: bool) -> None:
    """A1/A4: fixed and pinned entries count; a dynamic one is listed with the reason, in handoff status too."""
    repo, g = _gate(tmp_path, rev)
    assert g.passed is counts and g.approval_count == (2 if counts else 1)
    if not counts:
        assert any("routes models dynamically" in p and "pinned: true" in p for p in g.problems())
        row = next(r for r in reviewer_eligibility(repo, NODE, g, None) if r["model"] == "rev")
        assert not row["eligible"] and "routes models dynamically" in row["reason"]


def test_dynamic_routing_still_blocks_and_counts_without_distinct_families(tmp_path: Path) -> None:
    """A1: only the distinct-family count is affected: a block from a dynamic entry blocks, and with
    reviewers_distinct_families off its approval counts."""
    _repo, blocked = _gate(tmp_path / "a", ", routing: dynamic", rev_verdict="block")
    assert [b.model for b in blocked.blocks] == ["rev"] and not blocked.passed
    _repo, plain = _gate(tmp_path / "b", ", routing: dynamic", distinct=False)
    assert plain.passed and plain.approval_count == 2
