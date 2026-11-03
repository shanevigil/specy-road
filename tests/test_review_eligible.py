"""`handoff status` lists who on the roster can still supply a counting approval, and why the others cannot."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.review_repo_helpers import commit_file, git, make_review_repo, review_text
from tests.test_review_gate import TWO_FAMILIES

from specy_road.bundled_scripts import review_cli
from specy_road.review_files import reviews_dir


def _run(*args: str) -> int:
    with pytest.raises(SystemExit) as e:
        review_cli.main(list(args))
    return e.value.code


def _review(repo: Path, model: str, **kw) -> None:
    d = reviews_dir(repo, "M1.1")
    d.mkdir(parents=True, exist_ok=True)
    (d / f"REVIEW-{model}.md").write_text(review_text(git(repo, "rev-parse", "HEAD"), model=model, **kw))


def _ready(repo: Path, agent: str) -> None:
    d = reviews_dir(repo, "M1.1")
    d.mkdir(parents=True, exist_ok=True)
    (d / f"READY-{agent}.md").write_text(
        f"---\nnode_id: M1.1\nagent: {agent}\nbranch: feature/rm-thing\ncommit: {git(repo, 'rev-parse', 'HEAD')}\n"
        f"base: {git(repo, 'rev-parse', 'dev')}\nchanged_paths: [src/a.py]\n---\n"
    )


def _rows(repo: Path, capsys) -> dict[str, dict]:
    capsys.readouterr()
    _run("handoff", "status", "M1.1", "--json", "--repo-root", str(repo))
    st = json.loads(capsys.readouterr().out)["nodes"][0]
    return {r["model"]: r for r in st["reviewer_eligibility"]}


def test_human_is_listed_as_able_to_supply_the_missing_approval(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=TWO_FAMILIES)
    _review(repo, "opus")
    rows = _rows(repo, capsys)
    assert list(rows) == ["human", "opus", "sonnet", "sol", "composer", "astra"]
    assert rows["human"]["eligible"] and "mark-implementation-reviewed M1.1" in rows["human"]["reason"]
    assert rows["opus"]["eligible"] and rows["opus"]["reason"] == "its approval counts"
    assert rows["sol"]["eligible"]
    assert not rows["composer"]["eligible"] and "not a reviewer role" in rows["composer"]["reason"]


def test_same_family_reviewer_is_excluded(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=TWO_FAMILIES)
    _review(repo, "opus")
    sonnet = _rows(repo, capsys)["sonnet"]
    assert not sonnet["eligible"]
    assert sonnet["reason"] == "same family (anthropic) as opus's approval, which already counts"


def test_executor_and_fix_author_are_excluded(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=TWO_FAMILIES)
    _ready(repo, "opus")   # opus implemented the leaf
    notes = repo.parent / "notes-sol.md"
    notes.write_text(review_text(git(repo, "rev-parse", "HEAD"), model="sol", verdict="block", a1="fail"))
    assert _run("review", "record", "M1.1", "--model", "sol", "--verdict", "block",
                "--file", str(notes), "--repo-root", str(repo)) == 0
    commit_file(repo, "src/b.py", "x\n", "fix")
    _ready(repo, "sol")   # sol, having reviewed, wrote the fix
    rows = _rows(repo, capsys)
    assert not rows["opus"]["eligible"] and rows["opus"]["reason"] == "executor of the leaf (READY-opus.md)"
    assert not rows["sol"]["eligible"]
    assert rows["sol"]["reason"] == "wrote a fix commit on this leaf (READY-sol.md)"
    assert rows["human"]["eligible"] and rows["sonnet"]["eligible"]


def test_ready_author_with_a_counting_approval_is_still_excluded(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=TWO_FAMILIES)
    _ready(repo, "opus")
    _review(repo, "opus")   # the gate counts it: it trusts the record's authored_fix: false
    opus = _rows(repo, capsys)["opus"]
    assert not opus["eligible"] and opus["reason"] == "executor of the leaf (READY-opus.md)"


def test_second_same_family_approval_is_excluded_not_counting(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=TWO_FAMILIES)
    _review(repo, "opus")
    _review(repo, "sonnet")   # both counted by the gate, one family toward the policy
    rows = _rows(repo, capsys)
    assert rows["opus"]["eligible"] and rows["opus"]["reason"] == "its approval counts"
    assert not rows["sonnet"]["eligible"]
    assert rows["sonnet"]["reason"] == "same family (anthropic) as opus's approval, which already counts"


def test_rejected_record_is_excluded_with_the_gates_reason(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=TWO_FAMILIES)
    _review(repo, "sol", fresh=False)
    sol = _rows(repo, capsys)["sol"]
    assert not sol["eligible"]
    assert sol["reason"].startswith("rejected record REVIEW-sol.md: ") and "fresh reviewer session" in sol["reason"]


def test_text_lists_reviewers_below_the_policy_line_until_the_gate_is_met(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=TWO_FAMILIES)
    _review(repo, "opus")
    capsys.readouterr()
    assert _run("handoff", "status", "M1.1", "--repo-root", str(repo)) == 1
    lines = capsys.readouterr().out.splitlines()
    at = next(i for i, line in enumerate(lines) if line.startswith("  policy: 1/2"))
    assert lines[at + 1] == "  who can still supply a counting approval at this commit:"
    assert lines[at + 2].startswith("    human (human): can approve, interactively")
    assert "    sonnet (anthropic): excluded — same family (anthropic) as opus's approval, which already counts" in lines
    _review(repo, "sol")
    assert _rows(repo, capsys) == {}
