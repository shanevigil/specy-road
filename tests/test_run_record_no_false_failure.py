"""A reviewer run whose verdict was filed is complete with no error; one that filed nothing is not (M11.77).

Since M8.3 specy-road files the record from the reviewer's final JSON, so these runs answer with that JSON
instead of writing REVIEW-<model>.md themselves (a write M8.3 reports as a review failure).
"""

from __future__ import annotations

import json
from pathlib import Path

from tests.review_delegate_helpers import delegate_repo, set_steps, verdict_step
from tests.review_repo_helpers import commit_file
from tests.test_models_and_prompt import run_main
from tests.test_review_record_write import GENERIC   # a generic entry whose channels.cli runs the fake

from specy_road.bundled_scripts import role_prompt
from specy_road.review_delegate import delegate, load_run
from specy_road.review_files import review_path, reviews_dir

NO_RECORD = "no review record was filed"


def _prompt_cli(repo: Path) -> int:
    return run_main(role_prompt, "M1.1", "--model", "gem", "--role", "reviewer", "--channel", "cli", "--run",
                    "--repo-root", str(repo))


def _run_text(repo: Path) -> str:
    return (reviews_dir(repo, "M1.1") / "RUN-gem.json").read_text(encoding="utf-8")


def test_prompt_cli_run_whose_verdict_was_filed_is_complete_with_no_error(tmp_path: Path) -> None:
    repo, spec = delegate_repo(tmp_path, GENERIC)
    set_steps(repo, spec, {**verdict_step(repo, model="gem"), "plain": True})
    assert _prompt_cli(repo) == 0 and review_path(repo, "M1.1", "gem").exists()
    run = load_run(repo, "M1.1", "gem")
    assert run["state"] == "complete" and run["reason"] is None and run["events"] == []
    assert [a["error"] for a in run["attempts"]] == [None]
    assert NO_RECORD not in _run_text(repo)


def test_prompt_cli_run_without_a_verdict_files_nothing_and_is_incomplete(tmp_path: Path) -> None:
    repo, spec = delegate_repo(tmp_path, GENERIC)
    set_steps(repo, spec, {"raw": "reviewed, no JSON", "plain": True})
    assert _prompt_cli(repo) != 0 and not review_path(repo, "M1.1", "gem").exists()
    run = load_run(repo, "M1.1", "gem")
    assert run["state"] == "incomplete" and run["attempts"][0]["error"]
    assert run["events"][-1]["type"] == "reviewer-failure"


def test_prompt_cli_verdict_for_an_older_commit_is_not_filed(tmp_path: Path) -> None:
    repo, spec = delegate_repo(tmp_path, GENERIC)
    step = {**verdict_step(repo, model="gem"), "plain": True}
    commit_file(repo, "src/a.py", "print('moved')\n", "moved")      # the verdict now reviews an older commit
    set_steps(repo, spec, step)
    assert _prompt_cli(repo) != 0 and not review_path(repo, "M1.1", "gem").exists()
    assert load_run(repo, "M1.1", "gem")["state"] == "incomplete"


def test_delegate_run_whose_verdict_was_filed_has_no_error_in_the_run_file(tmp_path: Path) -> None:
    repo, spec = delegate_repo(tmp_path, GENERIC)
    set_steps(repo, spec, {**verdict_step(repo, model="gem"), "plain": True})
    assert delegate(repo, "M1.1", "gem", sleep=lambda s: None)["outcome"] == "recorded"
    run = json.loads(_run_text(repo))
    assert run["state"] == "complete" and run["reason"] is None and run["events"] == []
    assert [a["error"] for a in run["attempts"]] == [None] and NO_RECORD not in _run_text(repo)
