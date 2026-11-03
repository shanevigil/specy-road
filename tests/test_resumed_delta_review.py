"""``policy.reviewer_resumed_delta``: resumed sessions may approve an eligible delta (M11.36)."""

from __future__ import annotations

from pathlib import Path

from tests.review_repo_helpers import NODE, commit_file, git, make_review_repo, review_text

from specy_road.bundled_scripts.review_cli import _node_status
from specy_road.bundled_scripts.role_prompt import build_prompt
from specy_road.review_files import archive_review, reviews_dir
from specy_road.review_gate import evaluate_gate

ROSTER = """version: 1
roster:
  - {id: opus, family: anthropic, roles: [reviewer]}
  - {id: sol, family: openai, roles: [reviewer]}
policy: {reviewers_required: 2, reviewers_distinct_families: true%s}
"""
TEST_FILE = "src/tests/test_a.py"
TEST_SRC = "def test_a():\n    assert 1\n"


def _repo(tmp_path: Path, policy: str = "") -> tuple[Path, str]:
    repo = make_review_repo(tmp_path, orchestration=ROSTER % policy)
    approved = commit_file(repo, TEST_FILE, TEST_SRC, "first round")
    _file(repo, "opus", approved)
    return repo, approved


def _file(repo: Path, model: str, commit: str, *, fresh: bool = True, delta_from: str | None = None) -> None:
    text = review_text(commit, model=model, fresh=fresh)
    text = text.replace("notes\n", f"{model} notes on {commit[:7]}\n")
    if delta_from:
        text = text.replace("---\n", f"---\ndelta_from: '{delta_from}'\n", 1)
    d = reviews_dir(repo, "M1.1")
    d.mkdir(parents=True, exist_ok=True)
    (d / f"REVIEW-{model}.md").write_text(text)
    archive_review(repo, "M1.1", model, text)


def _fix(repo: Path) -> str:
    commit_file(repo, TEST_FILE, TEST_SRC + "\n\ndef test_b():\n    assert 2\n", "fix")
    return git(repo, "rev-parse", "HEAD")


def _why(repo: Path, model: str) -> str:
    gate = evaluate_gate(repo, NODE, git(repo, "rev-parse", "HEAD"))
    return next(why for r, why in gate.ineligible if r.data["model"] == model)


def test_resumed_delta_approval_counts_when_policy_allows(tmp_path: Path) -> None:
    repo, approved = _repo(tmp_path, ", reviewer_resumed_delta: true")
    head = _fix(repo)
    _file(repo, "opus", head, fresh=False, delta_from=approved)
    gate = evaluate_gate(repo, NODE, head)
    assert [a.model for a in gate.approvals] == ["opus"]
    _file(repo, "sol", head)
    assert evaluate_gate(repo, NODE, head).passed


def test_resumed_delta_refused_when_policy_off(tmp_path: Path) -> None:
    repo, approved = _repo(tmp_path)
    head = _fix(repo)
    _file(repo, "opus", head, fresh=False, delta_from=approved)
    why = _why(repo, "opus")
    assert "fresh reviewer session" in why and "reviewer_resumed_delta" in why
    st = _node_status(repo, "M1.1")
    assert any("reviewer_resumed_delta" in p for p in st["problems"])


def test_resumed_full_review_still_needs_fresh_session(tmp_path: Path) -> None:
    repo, _approved = _repo(tmp_path, ", reviewer_resumed_delta: true")
    head = _fix(repo)
    _file(repo, "opus", head, fresh=False)
    why = _why(repo, "opus")
    assert "fresh reviewer session" in why and "delta_from" in why
    assert evaluate_gate(repo, NODE, head).approvals == []


def test_delta_prompt_mentions_resumed_session_when_policy_on(tmp_path: Path) -> None:
    repo, approved = _repo(tmp_path, ", reviewer_resumed_delta: true")
    _fix(repo)
    (reviews_dir(repo, "M1.1") / "PACKET.md").write_text(
        f"**Commit under review:** `{git(repo, 'rev-parse', 'HEAD')}`\n", encoding="utf-8"
    )
    text, _, err = build_prompt(repo, "M1.1", role="reviewer", model="opus")
    assert err is None
    assert "fresh_session: false" in text and approved[:7] in text
