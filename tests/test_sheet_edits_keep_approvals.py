"""M11.16: planning or review bookkeeping after approval does not stale reviews."""

from __future__ import annotations

from pathlib import Path

from tests.review_repo_helpers import (
    NODE, commit_file, git, git_root_relative, make_layout_finish_repo, make_review_repo, review_text,
)
from tests.test_review_cli import ONE_AI, _status

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


def test_ours_merge_stales_approval(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    _review(repo)
    git(repo, "checkout", "-q", "-b", "other")
    commit_file(repo, "other.txt", "x\n", "other")
    git(repo, "checkout", "-q", "feature/rm-thing")
    git(repo, "merge", "-q", "-s", "ours", "--no-edit", "other")
    g = _gate(repo)
    assert not g.passed
    assert len(g.stale) == 1
    assert not g.bookkeeping_carry


def test_unresolved_commit_leaves_approval_stale(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    _review(repo)
    g = evaluate_gate(repo, NODE, None)
    assert not g.passed
    assert len(g.stale) == 1
    assert not g.bookkeeping_carry
    assert "still count" not in g.summary()


def test_nested_sheet_carry_and_git_root_namesake_stales(tmp_path: Path) -> None:
    git_top, project = make_layout_finish_repo(tmp_path / "keep", "nested")
    _review(project)
    commit_file(
        git_top,
        git_root_relative(git_top, project, NODE["planning_dir"]),
        "# M1.1 Thing\n\n## Intent\n\nUpdated.\n\n## References\n",
        "in-project sheet",
    )
    g = evaluate_gate(project, NODE, git(git_top, "rev-parse", "HEAD"))
    assert g.passed and g.bookkeeping_carry
    assert not g.stale

    for i, rel in enumerate((NODE["planning_dir"], "work/implementation-summary-M1.1.md")):
        git_top, project = make_layout_finish_repo(tmp_path / f"stale-{i}", "nested")
        _review(project)
        commit_file(git_top, rel, "git-root namesake\n", "git-root namesake")
        g = evaluate_gate(project, NODE, git(git_top, "rev-parse", "HEAD"))
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
