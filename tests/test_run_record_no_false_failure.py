"""A reviewer run that filed its record is complete with no error; 'no review record was filed' needs a missing one (M11.77)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from tests.review_delegate_helpers import (
    files_record_step,
    make_delegate_repo,
    roster,
    run_review_delegate,
    set_delegate_steps,
)
from tests.review_repo_helpers import commit_file, git, make_review_repo, review_text

from specy_road.bundled_scripts import role_prompt
from specy_road.review_delegate import load_run
from specy_road.review_files import reviews_dir

NO_RECORD = "no review record was filed"


def _cli_repo(tmp_path: Path) -> Path:
    """A repo whose ``opus`` cli copies ``record.md`` (when it exists) to REVIEW-opus.md, then exits 0."""
    script, record = tmp_path / "fake_cli.py", tmp_path / "record.md"
    repo = make_review_repo(tmp_path, orchestration=roster(f"{sys.executable} {script.as_posix()} {{prompt}}"))
    target = reviews_dir(repo, "M1.1") / "REVIEW-opus.md"
    script.write_text(f"import os, shutil\nprint('reviewing')\n"
                      f"if os.path.exists({str(record)!r}): shutil.copy({str(record)!r}, {str(target)!r})\n")
    target.parent.mkdir(parents=True, exist_ok=True)
    (target.parent / "PACKET.md").write_text("# Review packet\n\n**Commit under review:** HEAD\n")
    return repo


def _prompt_cli(repo: Path) -> int:
    with pytest.raises(SystemExit) as e:
        role_prompt.main(["M1.1", "--model", "opus", "--role", "reviewer", "--channel", "cli", "--repo-root", str(repo)])
    return e.value.code or 0


def _run_text(repo: Path) -> str:
    return (reviews_dir(repo, "M1.1") / "RUN-opus.json").read_text(encoding="utf-8")


def test_prompt_cli_run_that_filed_its_record_is_complete_with_no_error(tmp_path: Path) -> None:
    repo = _cli_repo(tmp_path)
    (tmp_path / "record.md").write_text(review_text(git(repo, "rev-parse", "HEAD"), model="opus"))
    assert _prompt_cli(repo) == 0
    run = load_run(repo, "M1.1", "opus")
    assert run["state"] == "complete" and run["reason"] is None and run["events"] == []
    assert [a["error"] for a in run["attempts"]] == [None]
    assert NO_RECORD not in _run_text(repo)


def test_prompt_cli_clean_exit_without_a_record_says_no_record_was_filed(tmp_path: Path) -> None:
    repo = _cli_repo(tmp_path)
    assert _prompt_cli(repo) == 0
    run = load_run(repo, "M1.1", "opus")
    assert run["state"] == "incomplete" and run["attempts"][0]["error"] == NO_RECORD
    assert run["events"][-1]["type"] == "reviewer-failure"


def test_prompt_cli_record_for_an_older_commit_is_not_this_commits_record(tmp_path: Path) -> None:
    repo = _cli_repo(tmp_path)
    (tmp_path / "record.md").write_text(review_text(git(repo, "rev-parse", "HEAD"), model="opus"))
    commit_file(repo, "src/a.py", "print('moved')\n", "moved")      # the record now reviews an older commit
    assert _prompt_cli(repo) == 0
    run = load_run(repo, "M1.1", "opus")
    assert run["state"] == "incomplete" and run["attempts"][0]["error"] == NO_RECORD


def test_delegate_run_that_filed_its_record_has_no_error_in_the_run_file(tmp_path: Path) -> None:
    repo, spec = make_delegate_repo(tmp_path)
    set_delegate_steps(repo, spec, files_record_step(repo))
    assert run_review_delegate(repo) == 0
    run = json.loads(_run_text(repo))
    assert run["state"] == "complete" and run["reason"] is None and run["events"] == []
    assert [a["error"] for a in run["attempts"]] == [None] and NO_RECORD not in _run_text(repo)
