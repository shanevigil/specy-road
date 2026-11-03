"""M11.16: planning or review bookkeeping after approval does not stale reviews."""

from __future__ import annotations

from pathlib import Path

from tests.review_repo_helpers import NODE, commit_file, git, make_review_repo, review_text
from tests.test_review_cli import ONE_AI, _run, _status

from specy_road.review_files import reviews_dir
from specy_road.review_gate import evaluate_gate


def _review(repo: Path) -> str:
    d = reviews_dir(repo, "M1.1")
    d.mkdir(parents=True, exist_ok=True)
    commit = git(repo, "rev-parse", "HEAD")
    (d / "REVIEW-human.md").write_text(review_text(commit, model="human"))
    return commit


def _gate(repo: Path):
    return evaluate_gate(repo, NODE, git(repo, "rev-parse", "HEAD"))


def test_sheet_only_delta_keeps_approval(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    _review(repo)
    assert _gate(repo).passed
    commit_file(repo, NODE["planning_dir"], "# M1.1 Thing\n\n## Intent\n\nUpdated.\n\n## References\n", "sheet")
    g = _gate(repo)
    assert g.passed and g.bookkeeping_carry
    assert not g.stale
    assert "still count" in g.summary()


def test_summary_only_delta_keeps_approval(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    _review(repo)
    commit_file(
        repo,
        "work/implementation-summary-M1.1.md",
        "# Summary\n\nDone.\n",
        "summary",
    )
    g = _gate(repo)
    assert g.passed and g.bookkeeping_carry
    assert not g.stale


def test_mixed_delta_stales_approval(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    _review(repo)
    commit_file(repo, NODE["planning_dir"], "# M1.1 Thing\n\n## Intent\n\nAlso.\n\n## References\n", "sheet")
    commit_file(repo, "src/b.py", "x\n", "code")
    g = _gate(repo)
    assert not g.passed
    assert len(g.stale) == 1
    assert not g.bookkeeping_carry


def test_handoff_status_reports_bookkeeping_carry(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    _review(repo)
    commit_file(repo, NODE["planning_dir"], "# M1.1 Thing\n\n## Intent\n\nNotes.\n\n## References\n", "sheet")
    st = _status(repo, capsys)
    assert st["policy_met"]
    assert "still count" in st["policy"]
