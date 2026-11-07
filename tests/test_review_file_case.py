"""Review records filed as ``review-<model>.md`` are found, reported and replaced under ``REVIEW-<model>.md``.

On macOS APFS a write to ``REVIEW-x.md`` keeps an existing ``review-x.md`` name, and a
case-sensitive ``REVIEW-`` match then misses the record. Each test writes the lowercase
file itself, so it passes the same way on a case-sensitive and a case-insensitive filesystem.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.review_repo_helpers import NODE, commit_file, git, make_review_repo, review_text
from tests.test_review_cli import ONE_AI

from specy_road.bundled_scripts import finish_task, mark_implementation_reviewed, review_cli
from specy_road.review_files import list_reviews, review_path, reviews_dir, write_review
from specy_road.review_gate import evaluate_gate, write_human_approval
from specy_road.review_rejected import rejected_state, unreadable_rejected_lines, write_rejected


def _run(*args: str) -> int:
    with pytest.raises(SystemExit) as e:
        review_cli.main(list(args))
    return e.value.code


def _lowercase_record(repo: Path, name: str = "review-opus.md", commit: str | None = None) -> Path:
    d = reviews_dir(repo, "M1.1")
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text(review_text(commit or git(repo, "rev-parse", "HEAD"), model="opus"), encoding="utf-8")
    return p


def test_write_review_replaces_a_name_that_differs_only_in_case(tmp_path: Path) -> None:
    d = tmp_path / "M1.1"
    d.mkdir()
    (d / "review-opus.md").write_text("old", encoding="utf-8")
    (d / "REVIEW-sonnet.md").write_text("other", encoding="utf-8")
    write_review(d / "REVIEW-opus.md", "new")
    assert sorted(p.name for p in d.iterdir()) == ["REVIEW-opus.md", "REVIEW-sonnet.md"]
    assert (d / "REVIEW-opus.md").read_text(encoding="utf-8") == "new"


def test_review_record_writes_the_canonical_name_over_a_lowercase_file(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    _lowercase_record(repo)
    notes = repo.parent / "notes.md"
    notes.write_text(review_text(git(repo, "rev-parse", "HEAD"), model="opus"), encoding="utf-8")
    assert _run("review", "record", "M1.1", "--model", "opus", "--verdict", "approve",
                "--file", str(notes), "--repo-root", str(repo)) == 0
    d = reviews_dir(repo, "M1.1")
    assert sorted(p.name for p in d.iterdir() if p.is_file()) == [".review-run.lock", "REVIEW-opus.md"]   # M21.27 lock
    assert "family: anthropic" in review_path(repo, "M1.1", "opus").read_text(encoding="utf-8")


@pytest.mark.parametrize("name", ["Review-OPUS.md", "review-opus.MD"])
def test_list_reviews_reports_a_lowercase_record_under_the_canonical_name(tmp_path: Path, name: str) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    real = _lowercase_record(repo, name)
    (r,) = list_reviews(repo, "M1.1")
    assert r.ok, r.errors
    assert r.path.name == "REVIEW-opus.md" and r.on_disk == real


@pytest.mark.parametrize("name", ["review-opus.md", "review-opus.MD"])
def test_the_gate_counts_a_lowercase_record_and_names_it_canonically(tmp_path: Path, name: str) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    _lowercase_record(repo, name)
    gate = evaluate_gate(repo, NODE, git(repo, "rev-parse", "HEAD"))
    assert gate.passed and [a.review.path.name for a in gate.approvals] == ["REVIEW-opus.md"]
    commit_file(repo, "src/b.py", "x\n", "fix")
    stale = evaluate_gate(repo, NODE, git(repo, "rev-parse", "HEAD"))
    assert not stale.passed
    assert any(p.startswith("REVIEW-opus.md: reviewed ") for p in stale.problems())


def test_handoff_status_and_review_list_report_a_lowercase_record(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    _lowercase_record(repo)
    capsys.readouterr()
    assert _run("handoff", "status", "M1.1", "--json", "--repo-root", str(repo)) == 0
    st = json.loads(capsys.readouterr().out)["nodes"][0]
    assert st["state"] == "approved" and st["policy_met"]
    assert [r["file"] for r in st["reviews"]] == ["REVIEW-opus.md"]
    assert st["review_rounds"]["rounds"] == 1
    assert _run("review", "list", "M1.1", "--repo-root", str(repo)) == 0
    out = capsys.readouterr().out
    assert "REVIEW-opus.md: approve by opus" in out and "review-opus.md" not in out
    assert "1/1 approvals, 0 block(s): met" in out


@pytest.mark.parametrize(("old", "canonical"), [("rejected-opus.md", "REJECTED-opus.md"),
                                                ("review-human.md", "REVIEW-human.md")])
def test_rejected_marker_and_human_approval_replace_a_case_variant(tmp_path: Path, old: str, canonical: str) -> None:
    """M22.19: both writers share write_review's case-variant unlink, so the stored name is canonical."""
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    d = reviews_dir(repo, "M1.1")
    d.mkdir(parents=True)
    (d / old).write_text("---\nnot: a marker\n", encoding="utf-8")
    head = git(repo, "rev-parse", "HEAD")
    if canonical.startswith("REJECTED"):
        write_rejected(d, "opus", head, "refused")
        assert rejected_state(d, "opus", head, repo) is not None
    else:
        write_human_approval(repo, NODE, head)
        assert [r.path.name for r in list_reviews(repo, "M1.1")] == [canonical]
    assert [p.name for p in d.iterdir() if p.is_file() and not p.name.startswith(".")] == [canonical]


def test_an_unreadable_rejected_marker_is_listed_whatever_its_case(tmp_path: Path) -> None:
    d = tmp_path / "M1.1"
    d.mkdir()
    (d / "rejected-opus.md").write_text("---\nnot: a marker\n---\n", encoding="utf-8")
    assert unreadable_rejected_lines(d) == [f"marker unreadable: {d / 'rejected-opus.md'}"]


def test_a_ready_that_is_not_utf8_is_refused_naming_the_file(tmp_path: Path, capsys) -> None:
    """M22.19 A7: a READY's author cannot be read, so the gate closes; no command shows a traceback."""
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    (repo / "work").mkdir()
    (repo / "work" / "implementation-summary-M1.1.md").write_text("## Summary\nDid it.\n")
    _lowercase_record(repo, "REVIEW-opus.md")
    (reviews_dir(repo, "M1.1") / "READY-sol.md").write_bytes(b"---\nnode_id: M1.1\nagent: sol \xff\n---\n")
    gate = evaluate_gate(repo, NODE, git(repo, "rev-parse", "HEAD"))
    assert not gate.passed and any(p.startswith("READY-sol.md is unreadable") for p in gate.problems())
    capsys.readouterr()
    assert _run("handoff", "status", "M1.1", "--repo-root", str(repo)) == 1
    assert "READY-sol.md is unreadable" in capsys.readouterr().out
    with pytest.raises(SystemExit) as e:
        mark_implementation_reviewed.main(["--yes", "--repo-root", str(repo)])
    assert e.value.code == 1 and "Traceback" not in capsys.readouterr().err
    reg = repo / "roadmap" / "registry.yaml"   # approved before the READY went bad: finish re-checks the gate
    reg.write_text(reg.read_text().replace("implementation_review: pending", "implementation_review: approved"))
    commit_file(repo, "roadmap/registry.yaml", reg.read_text(), "approved")
    with pytest.raises(SystemExit) as e:
        finish_task.main(["--repo-root", str(repo)])
    err = capsys.readouterr().err
    assert e.value.code == 1 and "Traceback" not in err and "READY-sol.md is unreadable" in err
