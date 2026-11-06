"""M21.35: an answer ``review record`` refuses gets one repair turn carrying the refusal text (D15, rc4 re-test).

The fake reviewer harness (tests/review_delegate_helpers.py) takes one answer per turn and records the prompt each
launch received, so each case checks what the reviewer was actually told.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.review_delegate_helpers import (CAPACITY, delegate_repo, fake_prompts, run_review_delegate, set_steps,
                                           verdict_step)
from tests.review_repo_helpers import NODE, git
from tests.test_review_record_write import GENERIC

from specy_road import review_files as rf
from specy_road.review_delegate import RESUME_PROMPT, delegate, load_run
from specy_road.reviewer_run_failure import run_path, save_run

# Approve notes `review record` refuses: each line is an observation with no 'not a defect because <reason>'.
REFUSED_LINES = ["The change looks fine overall", "A1 (pass): the prompt carries the rules and the tests pass"]
REFUSAL = "review record refused the output"


def refused_step(repo: Path, model: str = "opus", **extra) -> dict:
    step = verdict_step(repo, model=model)
    return {**step, "answer": {**step["answer"], "notes": "## Findings\n\n" + "\n".join(REFUSED_LINES)}, **extra}


def _delegate(repo: Path, model: str = "opus", retries: int = 3) -> dict:
    return delegate(repo, "M1.1", model, retries=retries, backoff=0, sleep=lambda _s: None)


def _repairs(run: dict) -> list[bool]:
    return [a.get("repair", False) for a in run["attempts"]]


def _carries_refusal(prompt: str | None) -> bool:
    return prompt is not None and all(line in prompt for line in REFUSED_LINES) and "not a defect because" in prompt


def test_a_refused_answer_gets_one_repair_turn_then_files(tmp_path: Path) -> None:
    repo, spec = delegate_repo(tmp_path)
    set_steps(repo, spec, refused_step(repo), verdict_step(repo))
    run = _delegate(repo)
    assert run["state"] == "complete" and run["outcome"] == "recorded", run["reason"]
    assert rf.review_path(repo, "M1.1", "opus").is_file()
    assert _repairs(run) == [False, True]
    assert all(line in run["refusal"] for line in REFUSED_LINES)   # review record's whole output, kept
    prompts = fake_prompts(spec)
    assert len(prompts) == 2 and not _carries_refusal(prompts[0]) and _carries_refusal(prompts[1])
    assert "Send the whole corrected JSON object" in prompts[1]


def test_a_second_refusal_leaves_the_run_incomplete_naming_both(tmp_path: Path) -> None:
    repo, spec = delegate_repo(tmp_path)
    set_steps(repo, spec, refused_step(repo))
    assert run_review_delegate(repo) == 1
    run = load_run(repo, "M1.1", "opus")
    assert run["state"] == "incomplete" and _repairs(run) == [False, True]
    assert run["reason"].count(REFUSAL) == 2 and "after the repair turn" in run["reason"]
    assert not rf.review_path(repo, "M1.1", "opus").exists()


@pytest.mark.parametrize("case", ["files", "writes", "no-json"])
def test_no_repair_turn_unless_review_record_refused(tmp_path: Path, case: str) -> None:
    repo, spec = delegate_repo(tmp_path)
    step = {"files": verdict_step(repo), "no-json": {},
            "writes": {**verdict_step(repo), "write": {"path": str(repo / "src" / "x.py"), "text": "x\n"}}}[case]
    set_steps(repo, spec, step, verdict_step(repo))
    run = _delegate(repo)
    assert len(fake_prompts(spec)) == 1 and _repairs(run) == [False] and "refusal" not in run
    assert run["outcome"] == {"files": "recorded", "writes": "review_failure", "no-json": "rerun"}[case]


def test_a_repair_turn_that_writes_a_tracked_file_is_a_review_failure(tmp_path: Path) -> None:
    repo, spec = delegate_repo(tmp_path)
    sheet = repo / NODE["planning_dir"]
    assert git(repo, "ls-files", NODE["planning_dir"])                     # tracked
    set_steps(repo, spec, refused_step(repo), {**verdict_step(repo), "write": {"path": str(sheet), "text": "x\n"}})
    run = _delegate(repo)
    assert run["state"] == "incomplete" and run["outcome"] == "review_failure" and _repairs(run) == [False, True]
    assert NODE["planning_dir"] in run["reason"]
    assert not rf.review_path(repo, "M1.1", "opus").exists()


def test_a_repair_turn_reporting_another_model_files_a_mismatch(tmp_path: Path) -> None:
    repo, spec = delegate_repo(tmp_path)
    set_steps(repo, spec, refused_step(repo), {**verdict_step(repo), "model": "gpt-5.6-sol"})
    run = _delegate(repo)
    assert run["outcome"] == "recorded" and run["reported_model"] == "gpt-5.6-sol"
    rec = rf.load_review(rf.review_path(repo, "M1.1", "opus"), ["A1", "A2"])
    assert rec.ok and rec.data["model_mismatch"] is True and rec.data["harness_model"] == "gpt-5.6-sol"


def test_a_capacity_retry_inside_the_repair_turn_keeps_the_refusal(tmp_path: Path) -> None:
    repo, spec = delegate_repo(tmp_path)
    set_steps(repo, spec, refused_step(repo), {"error": CAPACITY, "exit": 1}, verdict_step(repo))
    run = _delegate(repo, retries=2)
    assert run["outcome"] == "recorded" and _repairs(run) == [False, True, True]
    assert [a["capacity"] for a in run["attempts"]] == [False, True, False]
    prompts = fake_prompts(spec)
    assert len(prompts) == 3 and _carries_refusal(prompts[1]) and _carries_refusal(prompts[2])


def test_a_non_resumable_harness_gets_one_fresh_launch_with_the_full_prompt_and_the_refusal(tmp_path: Path) -> None:
    repo, spec = delegate_repo(tmp_path, GENERIC)
    refused = refused_step(repo, model="gem")["answer"]
    set_steps(repo, spec, {"plain": True, "raw": json.dumps(refused)},
              {"plain": True, "raw": json.dumps(verdict_step(repo, model="gem")["answer"])})
    run = _delegate(repo, model="gem")
    assert run["outcome"] == "recorded" and _repairs(run) == [False, True], run["reason"]
    prompts = fake_prompts(spec)
    assert len(prompts) == 2 and "## Your role: reviewer" in prompts[1] and _carries_refusal(prompts[1])


@pytest.mark.parametrize("stored,repairs", [({}, True), ({"state": "complete"}, False), ({"refusal": 7}, False),
                                            ({"refusal": None}, False)],
                         ids=["incomplete-refused", "complete", "non-string", "no-refusal"])
def test_resume_sends_a_stored_refusal_only_on_an_incomplete_run(tmp_path: Path, stored: dict,
                                                                 repairs: bool) -> None:
    repo, spec = delegate_repo(tmp_path)
    set_steps(repo, spec, refused_step(repo))
    assert _delegate(repo)["state"] == "incomplete"                   # refused twice: the refusal is kept
    path = run_path(repo, "M1.1", "opus")
    save_run(path, {**load_run(repo, "M1.1", "opus"), **stored})
    set_steps(repo, spec, verdict_step(repo))
    assert run_review_delegate(repo, "--resume") == 0
    sent = fake_prompts(spec)
    assert len(sent) == 3 and _carries_refusal(sent[-1]) is repairs   # the two refused turns, then the resume
    assert (sent[-1] == RESUME_PROMPT) is not repairs
