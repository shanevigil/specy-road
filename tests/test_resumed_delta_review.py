"""``policy.reviewer_resumed_delta``: a resumed reviewer session may approve an eligible delta (M11.36)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.review_repo_helpers import NODE, commit_file, git, make_review_repo, review_text

from specy_road.bundled_scripts import review_cli
from specy_road.bundled_scripts.role_prompt import build_prompt
from specy_road.review_files import archive_review, reviews_dir
from specy_road.review_gate import evaluate_gate

ROSTER = """version: 1
roster:
  - {id: opus, family: anthropic, roles: [reviewer]}
  - {id: sol, family: openai, roles: [reviewer]}
policy: {reviewers_required: 2, reviewers_distinct_families: true%s}
"""
ON = ", reviewer_resumed_delta: true"
TEST_FILE = "src/tests/test_a.py"
TEST_SRC = "def test_a():\n    assert 1\n"
ONLY = "policy requires a fresh reviewer session (fresh_session: true), the only reason it does not count"


def _repo(tmp_path: Path, policy: str = "") -> tuple[Path, str]:
    repo = make_review_repo(tmp_path, orchestration=ROSTER % policy)
    approved = commit_file(repo, TEST_FILE, TEST_SRC, "first round")
    _file(repo, "opus", approved)
    return repo, approved


def _file(repo: Path, model: str, commit: str, *, fresh: bool = True, delta_from: str | None = None,
          verdict: str = "approve") -> None:
    text = review_text(commit, model=model, fresh=fresh, verdict=verdict)
    text = text.replace("notes\n", f"{model} notes on {commit[:7]}\n")
    if delta_from:
        text = text.replace("---\n", f"---\ndelta_from: '{delta_from}'\n", 1)
    d = reviews_dir(repo, "M1.1")
    d.mkdir(parents=True, exist_ok=True)
    (d / f"REVIEW-{model}.md").write_text(text)
    archive_review(repo, "M1.1", model, text)


def _fix(repo: Path, rel: str = TEST_FILE) -> str:
    return commit_file(repo, rel, TEST_SRC + "\n\ndef test_b():\n    assert 2\n", "fix")


def _why(repo: Path, model: str = "opus") -> str:
    gate = evaluate_gate(repo, NODE, git(repo, "rev-parse", "HEAD"))
    return next(why for r, why in gate.ineligible if r.data["model"] == model)


def _status_problems(repo: Path, capsys) -> list[str]:
    capsys.readouterr()
    with pytest.raises(SystemExit):
        review_cli.main(["handoff", "status", "M1.1", "--json", "--repo-root", str(repo)])
    return json.loads(capsys.readouterr().out)["nodes"][0]["problems"]


def test_resumed_delta_approval_counts_when_policy_allows(tmp_path: Path) -> None:
    repo, approved = _repo(tmp_path, ON)
    head = _fix(repo)
    _file(repo, "opus", head, fresh=False, delta_from=approved)
    assert [a.model for a in evaluate_gate(repo, NODE, head).approvals] == ["opus"]
    _file(repo, "sol", head)
    assert evaluate_gate(repo, NODE, head).passed


def test_resumed_delta_approval_still_meets_the_delta_rules(tmp_path: Path) -> None:
    repo, approved = _repo(tmp_path, ON)
    head = _fix(repo, "src/app.py")   # not a documentation or test file: no delta
    _file(repo, "opus", head, fresh=False, delta_from=approved)
    assert evaluate_gate(repo, NODE, head).approvals == []
    assert "src/app.py is not a documentation or test file; a full review is needed" in _why(repo)


def test_resumed_delta_refused_when_policy_off(tmp_path: Path, capsys) -> None:
    repo, approved = _repo(tmp_path)
    head = _fix(repo)
    _file(repo, "opus", head, fresh=False, delta_from=approved)
    assert evaluate_gate(repo, NODE, head).approvals == []
    note = f"{ONLY}; with policy.reviewer_resumed_delta: true this resumed delta approval would count"
    assert _why(repo) == note
    assert f"REVIEW-opus.md: does not count — {note}" in _status_problems(repo, capsys)


def test_policy_off_says_when_the_delta_would_not_qualify_anyway(tmp_path: Path) -> None:
    repo, approved = _repo(tmp_path)
    head = _fix(repo, "src/app.py")
    _file(repo, "opus", head, fresh=False, delta_from=approved)
    assert _why(repo).startswith(f"{ONLY}; with policy.reviewer_resumed_delta: true it would still not count: "
                                 f"a delta review from {approved}, but src/app.py is not a documentation or test file")


def test_resumed_full_review_still_needs_fresh_session(tmp_path: Path, capsys) -> None:
    repo, approved = _repo(tmp_path, ON)
    head = _fix(repo)
    _file(repo, "opus", head, fresh=False)
    assert evaluate_gate(repo, NODE, head).approvals == []
    note = f"{ONLY}; a resumed delta approval naming delta_from: {approved} would count"
    assert _why(repo) == note
    assert f"REVIEW-opus.md: does not count — {note}" in _status_problems(repo, capsys)


def test_resumed_full_review_names_the_key_when_policy_off(tmp_path: Path) -> None:
    repo, approved = _repo(tmp_path)
    head = _fix(repo)
    _file(repo, "opus", head, fresh=False)
    assert _why(repo) == (f"{ONLY}; a resumed delta approval naming delta_from: {approved} would count "
                          "with policy.reviewer_resumed_delta: true")


def test_resumed_review_without_an_earlier_approval_needs_a_fresh_full_review(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path, orchestration=ROSTER % ON)
    _file(repo, "opus", git(repo, "rev-parse", "HEAD"), fresh=False)
    assert _why(repo) == (f"{ONLY}; a resumed delta approval would not count either (no earlier approval): "
                          "a fresh full review is needed")


def test_another_failing_check_is_not_reported_as_fresh_session_only(tmp_path: Path) -> None:
    repo, _approved = _repo(tmp_path, ", reviewer_reruns_required: true")
    head = _fix(repo)
    _file(repo, "opus", head, fresh=False)
    assert _why(repo) == ("policy requires a fresh reviewer session (fresh_session: true); "
                          "approved without re-running a command (policy.reviewer_reruns_required)")


def test_resumed_delta_approval_is_a_basis_for_the_next_delta(tmp_path: Path) -> None:
    repo, approved = _repo(tmp_path, ON)
    second = _fix(repo)
    _file(repo, "opus", second, fresh=False, delta_from=approved)
    third = commit_file(repo, "src/tests/test_c.py", "def test_c():\n    assert 3\n", "fix again")
    _file(repo, "opus", third, fresh=False, delta_from=second)
    assert [a.model for a in evaluate_gate(repo, NODE, third).approvals] == ["opus"]


@pytest.mark.parametrize("policy, said", [
    (ON, "You may read it in the session that approved"),
    ("", "Read it in a fresh session (`fresh_session: true`); a resumed session counts only when"),
])
def test_delta_packet_says_whether_a_resumed_session_may_approve(tmp_path: Path, policy: str, said: str) -> None:
    repo, approved = _repo(tmp_path, policy)
    _fix(repo)
    (reviews_dir(repo, "M1.1") / "PACKET.md").write_text(
        f"**Commit under review:** `{git(repo, 'rev-parse', 'HEAD')}`\n", encoding="utf-8")
    text, _, err = build_prompt(repo, "M1.1", role="reviewer", model="opus")
    assert err is None
    assert "## Delta review" in text and said in text and f'delta_from: "{approved}"' in text
    assert ("set `fresh_session: false`" in text) == bool(policy)
    resumed = "If you are the session that approved the commit this delta starts from, resumed for this round"
    assert (resumed in text) == bool(policy) and ("This is a fresh session;" in text) != bool(policy)


def test_full_packet_prompt_still_says_fresh_session_when_policy_on(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path, orchestration=ROSTER % ON)
    (reviews_dir(repo, "M1.1")).mkdir(parents=True, exist_ok=True)
    (reviews_dir(repo, "M1.1") / "PACKET.md").write_text("full packet\n", encoding="utf-8")
    text, _, err = build_prompt(repo, "M1.1", role="reviewer", model="opus")
    assert err is None and "This is a fresh session;" in text and "resumed for this round" not in text


def test_resumed_delta_block_counts_when_policy_allows(tmp_path: Path) -> None:
    repo, approved = _repo(tmp_path, ON)
    head = _fix(repo)
    _file(repo, "opus", head, fresh=False, delta_from=approved, verdict="block")
    assert [b.model for b in evaluate_gate(repo, NODE, head).blocks] == ["opus"]


def test_resumed_block_reasons(tmp_path: Path) -> None:
    repo, approved = _repo(tmp_path)
    head = _fix(repo)
    _file(repo, "opus", head, fresh=False, delta_from=approved, verdict="block")
    assert _why(repo) == f"{ONLY}; with policy.reviewer_resumed_delta: true this resumed block would count"
    _file(repo, "opus", head, fresh=False, verdict="block")
    assert _why(repo) == (f"{ONLY}; a resumed block counts only when it names delta_from "
                          "and policy.reviewer_resumed_delta is on")
