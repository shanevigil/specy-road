"""M21.35: an answer ``review record`` refuses gets one repair turn carrying the refusal text (D15, rc4 re-test).
M21.42: so does an answer that does not parse after a clean last attempt, carrying specy-road's reading of it.

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
PARSE_INTRO = "## Your final message could not be read"
NO_JSON = "the final message holds no JSON object"


def refused_step(repo: Path, model: str = "opus", **extra) -> dict:
    step = verdict_step(repo, model=model)
    return {**step, "answer": {**step["answer"], "notes": "## Findings\n\n" + "\n".join(REFUSED_LINES)}, **extra}


def _delegate(repo: Path, model: str = "opus", retries: int = 3) -> dict:
    return delegate(repo, "M1.1", model, retries=retries, backoff=0, sleep=lambda _s: None)


def _carries_refusal(prompt: str | None) -> bool:
    return prompt is not None and all(line in prompt for line in REFUSED_LINES) and "not a defect because" in prompt


def _carries_parse(prompt: str | None, reason: str) -> bool:
    return prompt is not None and PARSE_INTRO in prompt and reason in prompt


def _turns(spec: Path, run: dict, skip: int = 0) -> list[bool]:
    """Each attempt's ``repair`` flag, once the prompt its launch received (after the first ``skip`` launches) is
    checked against it: a repair attempt's carries every refused line and "not a defect because" (a ``record``
    refusal) or the parse intro and the stored reason (``parse``, M21.42), any other's does not. Every case reads
    the flags through this, so none checks the run record without the prompts sent."""
    flags = [a.get("repair", False) for a in run["attempts"]]
    parse = run.get("refusal_kind") == "parse"
    assert [_carries_parse(p, run["refusal"]) if parse else _carries_refusal(p)
            for p in fake_prompts(spec)[skip:]] == flags
    return flags


def test_a_refused_answer_gets_one_repair_turn_then_files(tmp_path: Path) -> None:
    repo, spec = delegate_repo(tmp_path)
    set_steps(repo, spec, refused_step(repo), verdict_step(repo))
    run = _delegate(repo)
    assert run["state"] == "complete" and run["outcome"] == "recorded", run["reason"]
    assert rf.review_path(repo, "M1.1", "opus").is_file()
    assert _turns(spec, run) == [False, True]
    assert all(line in run["refusal"] for line in REFUSED_LINES)   # review record's whole output, kept
    assert "Send the whole corrected JSON object" in fake_prompts(spec)[1]


@pytest.mark.parametrize("first,second", [("refused", "refused"), ("parse", "parse"), ("parse", "refused"),
                                          ("refused", "parse")])
def test_a_second_failure_leaves_the_run_incomplete_naming_both(tmp_path: Path, first: str, second: str) -> None:
    repo, spec = delegate_repo(tmp_path)
    steps = {"refused": refused_step(repo), "parse": {}}
    set_steps(repo, spec, steps[first], steps[second])
    assert run_review_delegate(repo) == 1
    run = load_run(repo, "M1.1", "opus")
    assert run["state"] == "incomplete" and _turns(spec, run) == [False, True]   # no third turn
    assert run["refusal_kind"] == {"refused": "record", "parse": "parse"}[first]
    said = {"refused": REFUSAL, "parse": NO_JSON}
    head, tail = run["reason"].split("; after the repair turn, ")
    assert said[first] in head and said[second] in tail
    assert not rf.review_path(repo, "M1.1", "opus").exists()


def _valid_json(repo: Path) -> str:
    return json.dumps(verdict_step(repo)["answer"])


@pytest.mark.parametrize("case,reason", [
    ("fenced", "does not end with a JSON object"), ("prose-after", "does not end with a JSON object"),
    ("no-json", NO_JSON), ("unfinished", "ends inside an unfinished JSON object"),
    ("schema-invalid", "does not match the review output schema")])
def test_an_unparseable_answer_gets_one_repair_turn_then_files(tmp_path: Path, case: str, reason: str) -> None:
    repo, spec = delegate_repo(tmp_path)
    valid = _valid_json(repo)
    step = {"fenced": {"raw": f"```json\n{valid}\n```"}, "prose-after": {"raw": valid + "\nThat is my review."},
            "no-json": {}, "unfinished": {"raw": valid[:-20]},
            "schema-invalid": {"answer": {**verdict_step(repo)["answer"], "verdict": "maybe"}}}[case]
    set_steps(repo, spec, step, verdict_step(repo))
    run = _delegate(repo)
    assert run["state"] == "complete" and run["outcome"] == "recorded", run["reason"]
    assert run["refusal_kind"] == "parse" and reason in run["refusal"] and _turns(spec, run) == [False, True]
    repair = fake_prompts(spec)[1]
    assert "## Your answer was refused" not in repair and "not a defect because" not in repair   # no notes rules
    assert "no code fence" in repair
    if case == "schema-invalid":
        assert f"```\n{run['refusal']}\n```" in repair


@pytest.mark.parametrize("case", ["files", "writes", "writes-unparseable", "capacity", "exit", "refused-exit"])
def test_no_repair_turn_without_a_refusal_or_a_clean_parse_failure(tmp_path: Path, case: str) -> None:
    repo, spec = delegate_repo(tmp_path)
    write = {"write": {"path": str(repo / "src" / "x.py"), "text": "x\n"}}
    step = {"files": verdict_step(repo), "writes": {**verdict_step(repo), **write},
            "writes-unparseable": {"raw": "not a verdict", **write}, "capacity": {"error": CAPACITY, "exit": 1},
            "exit": {"raw": "not a verdict", "exit": 2}, "refused-exit": refused_step(repo, exit=2)}[case]
    set_steps(repo, spec, step, verdict_step(repo))
    run = _delegate(repo, retries=0)
    assert _turns(spec, run) == [False] and "refusal" not in run
    assert run["outcome"] == {"files": "recorded", "writes": "review_failure", "writes-unparseable": "review_failure",
                              "capacity": "rerun", "exit": "rerun", "refused-exit": "rerun"}[case]
    assert len(fake_prompts(spec)) == 1   # one launch: the non-zero exit gets no repair turn, refused or not
    assert case != "refused-exit" or REFUSAL in run["reason"]   # review record did refuse it


def test_a_repair_turn_that_writes_a_tracked_file_is_a_review_failure(tmp_path: Path) -> None:
    repo, spec = delegate_repo(tmp_path)
    sheet = repo / NODE["planning_dir"]
    assert git(repo, "ls-files", NODE["planning_dir"])                     # tracked
    set_steps(repo, spec, refused_step(repo), {**verdict_step(repo), "write": {"path": str(sheet), "text": "x\n"}})
    run = _delegate(repo)
    assert run["state"] == "incomplete" and run["outcome"] == "review_failure" and _turns(spec, run) == [False, True]
    assert NODE["planning_dir"] in run["reason"]
    assert not rf.review_path(repo, "M1.1", "opus").exists()


def test_a_repair_turn_reporting_another_model_files_a_mismatch(tmp_path: Path) -> None:
    repo, spec = delegate_repo(tmp_path)
    set_steps(repo, spec, refused_step(repo), {**verdict_step(repo), "model": "gpt-5.6-sol"})
    run = _delegate(repo)
    assert run["outcome"] == "recorded" and run["reported_model"] == "gpt-5.6-sol"
    assert _turns(spec, run) == [False, True]
    rec = rf.load_review(rf.review_path(repo, "M1.1", "opus"), ["A1", "A2"])
    assert rec.ok and rec.data["model_mismatch"] is True and rec.data["harness_model"] == "gpt-5.6-sol"


def test_a_capacity_retry_inside_the_repair_turn_keeps_the_refusal(tmp_path: Path) -> None:
    repo, spec = delegate_repo(tmp_path)
    set_steps(repo, spec, refused_step(repo), {"error": CAPACITY, "exit": 1}, verdict_step(repo))
    run = _delegate(repo, retries=2)
    assert run["outcome"] == "recorded" and _turns(spec, run) == [False, True, True]   # the retry carries it
    assert [a["capacity"] for a in run["attempts"]] == [False, True, False]


@pytest.mark.parametrize("kind", ["record", "parse"])
def test_a_non_resumable_harness_gets_one_fresh_launch_with_the_full_prompt_and_the_refusal(tmp_path: Path,
                                                                                         kind: str) -> None:
    repo, spec = delegate_repo(tmp_path, GENERIC)
    refused = refused_step(repo, model="gem")["answer"]
    set_steps(repo, spec, {"plain": True, "raw": json.dumps(refused) if kind == "record" else "no verdict here"},
              {"plain": True, "raw": json.dumps(verdict_step(repo, model="gem")["answer"])})
    run = _delegate(repo, model="gem")
    assert run["outcome"] == "recorded" and _turns(spec, run) == [False, True], run["reason"]
    assert run["refusal_kind"] == kind
    assert "## Your role: reviewer" in fake_prompts(spec)[1]   # one fresh launch: the full prompt plus the refusal


@pytest.mark.parametrize("stored,repairs", [({}, True), ({"state": "complete"}, False), ({"refusal": 7}, False),
                                            ({"refusal": None}, False)],
                         ids=["incomplete-refused", "complete", "non-string", "no-refusal"])
def test_resume_sends_a_stored_refusal_only_on_an_incomplete_run(tmp_path: Path, stored: dict,
                                                                 repairs: bool) -> None:
    repo, spec = delegate_repo(tmp_path)
    set_steps(repo, spec, refused_step(repo))
    first = _delegate(repo)
    assert first["state"] == "incomplete" and _turns(spec, first) == [False, True]   # refused twice: kept
    path = run_path(repo, "M1.1", "opus")
    save_run(path, {**load_run(repo, "M1.1", "opus"), **stored})
    calls = len(fake_prompts(spec))   # the fake picks its step by launch count: the resume hits capacity, then files
    set_steps(repo, spec, *[{"error": CAPACITY, "exit": 1}] * (calls + 1), verdict_step(repo))
    assert run_review_delegate(repo, "--resume") == 0
    run = load_run(repo, "M1.1", "opus")
    assert run["state"] == "complete" and _turns(spec, run, calls) == [repairs, repairs]   # the retry carries it too
    assert all((p == RESUME_PROMPT) is not repairs for p in fake_prompts(spec)[calls:])


@pytest.mark.parametrize("kind,then", [("parse", "files"), ("parse", "fails"), ("record", "files")],
                         ids=["parse", "parse-fails-again", "legacy-record"])
def test_resume_sends_the_repair_pair_for_the_stored_kind(tmp_path: Path, kind: str, then: str) -> None:
    repo, spec = delegate_repo(tmp_path)
    set_steps(repo, spec, {} if kind == "parse" else refused_step(repo))
    first = _delegate(repo)
    assert first["state"] == "incomplete" and first["refusal_kind"] == kind and _turns(spec, first) == [False, True]
    if kind == "record":   # a record written before M21.42 has no refusal_kind: a record refusal
        path = run_path(repo, "M1.1", "opus")
        save_run(path, {k: v for k, v in load_run(repo, "M1.1", "opus").items() if k != "refusal_kind"})
    calls = len(fake_prompts(spec))
    set_steps(repo, spec, *[{}] * calls, verdict_step(repo) if then == "files" else {})
    assert run_review_delegate(repo, "--resume") == (0 if then == "files" else 1)
    run = load_run(repo, "M1.1", "opus")
    assert run["refusal_kind"] == kind and _turns(spec, run, calls) == [True]   # one turn, the repair pair's
    (resumed,) = fake_prompts(spec)[calls:]
    assert resumed != RESUME_PROMPT
    if kind == "parse":
        assert "## Your answer was refused" not in resumed and "not a defect because" not in resumed
    if then == "fails":
        assert run["state"] == "incomplete" and run["reason"].count(NO_JSON) == 2
        assert "after the repair turn" in run["reason"] and not rf.review_path(repo, "M1.1", "opus").exists()
