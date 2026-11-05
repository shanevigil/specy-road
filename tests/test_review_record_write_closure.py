"""M8.3 A2/A3 regressions from Sol's block at 27d39730, through the public CLIs and ``delegate``.

F1: the run lock ``.review-run.lock`` is not a runtime file: a reviewer that overwrites it in place fails the review.
F2: ``prompt --channel cli`` closes its run from the filing outcome, so a review failure or rerun request stays
incomplete even when an older record of the same commit is on file.
F3: a terminal Codex ``agent_message`` with no text replaces an earlier answer of the turn: a rerun request.
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path

import pytest

from tests.review_delegate_helpers import delegate_repo, set_steps, verdict_step, wrote_only
from tests.review_repo_helpers import git, make_review_repo, review_output
from tests.test_models_and_prompt import run_main

from specy_road import review_files as rf
from specy_road.bundled_scripts import review_cli, role_prompt
from specy_road.review_delegate import delegate, load_run
from specy_road.reviewer_run_failure import run_path, save_run


def test_an_in_place_overwrite_of_the_run_lock_is_a_review_failure_and_files_no_verdict(tmp_path: Path,
                                                                                        capsys) -> None:
    repo, spec = delegate_repo(tmp_path)
    lock = rf.reviews_dir(repo, "M1.1") / ".review-run.lock"
    set_steps(repo, spec, {**verdict_step(repo), "write": {"path": str(lock), "text": "taken\n"}})
    with pytest.raises(SystemExit) as e:
        review_cli.main(["review", "delegate", "M1.1", "--model", "opus", "--backoff", "0", "--json",
                         "--repo-root", str(repo)])
    run = json.loads(capsys.readouterr().out)
    assert lock.read_text() == "taken\n"                                     # written in place, no new entry
    assert e.value.code == 1 and run["outcome"] == "review_failure"
    assert wrote_only(run["reason"], "work/reviews/M1.1/.review-run.lock")
    assert not rf.review_path(repo, "M1.1", "opus").exists()


@pytest.mark.parametrize("state", ["rerun", "review_failure"])
def test_prompt_cli_keeps_a_failed_filing_incomplete_beside_an_older_record_of_the_commit(tmp_path: Path, capsys,
                                                                                          state: str) -> None:
    repo, spec = delegate_repo(tmp_path)
    second = ({"raw": "not a verdict"} if state == "rerun"
              else {**verdict_step(repo, "block"), "write": {"path": str(repo / "src" / "a.py"), "text": "x\n"}})
    set_steps(repo, spec, verdict_step(repo), second)
    assert delegate(repo, "M1.1", "opus", sleep=lambda _s: None)["outcome"] == "recorded"   # the older record
    older = rf.review_path(repo, "M1.1", "opus").read_bytes()
    assert run_main(role_prompt, "M1.1", "--model", "opus", "--role", "reviewer", "--channel", "cli",
                    "--repo-root", str(repo)) == 1
    run = load_run(repo, "M1.1", "opus")
    assert run["source"] == "prompt-cli" and run["state"] == "incomplete" and run["outcome"] == state
    said = "rerun requested" if state == "rerun" else "review failure"
    assert said in run["reason"] and run["events"][-1]["type"] == "reviewer-failure"
    assert said in run["events"][-1]["error"]
    assert rf.review_path(repo, "M1.1", "opus").read_bytes() == older       # untouched, and not this run's success
    assert said in capsys.readouterr().err


FAKE_CODEX_RESUME = '''#!{python}
import json, os, sys
spec = json.loads(open(os.environ["FAKE_CODEX_SPEC"]).read())
open(spec["calls"], "w").write(json.dumps(sys.argv[1:]))
sys.stdin.read()
print(json.dumps({{"type": "item.completed", "item": {{"type": "agent_message", "text": json.dumps(spec["answer"])}}}}))
if spec["null_last"]:   # the terminal answer event carries no answer
    print(json.dumps({{"type": "item.completed", "item": {{"type": "agent_message", "text": None}}}}))
print(json.dumps({{"type": "turn.completed", "usage": {{}}}}), flush=True)
'''


@pytest.mark.parametrize("null_last", [True, False])
def test_a_codex_resume_whose_last_answer_event_has_no_text_is_a_rerun(tmp_path: Path, monkeypatch,
                                                                       null_last: bool) -> None:
    repo = make_review_repo(tmp_path, orchestration=(
        "version: 1\nroster:\n  - {id: human, family: human, roles: [coordinator, reviewer]}\n"
        "  - {id: sol, family: openai, roles: [reviewer], harness: codex}\n"))
    rf.reviews_dir(repo, "M1.1").mkdir(parents=True)
    head, sid = git(repo, "rev-parse", "HEAD"), str(uuid.uuid4())
    save_run(run_path(repo, "M1.1", "sol"), {"node_id": "M1.1", "model": "sol", "harness": "codex", "commit": head,
                                             "session_id": sid, "state": "incomplete", "attempts": [], "events": []})
    bin_dir, spec = tmp_path / "bin", tmp_path / "codex-spec.json"
    bin_dir.mkdir()
    (bin_dir / "codex").write_text(FAKE_CODEX_RESUME.format(python=sys.executable))
    (bin_dir / "codex").chmod(0o755)
    spec.write_text(json.dumps({"calls": str(tmp_path / "codex-calls.json"), "null_last": null_last,
                                "answer": review_output(head, model="sol")}))
    monkeypatch.setenv("FAKE_CODEX_SPEC", str(spec))
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")
    run = delegate(repo, "M1.1", "sol", resume=True, sleep=lambda _s: None)
    argv = json.loads((tmp_path / "codex-calls.json").read_text())
    assert argv[:2] == ["exec", "resume"] and sid in argv and "-o" not in argv   # a resume: no -o file
    if null_last:
        assert run["outcome"] == "rerun" and run["state"] == "incomplete"
        assert "no JSON object" in run["reason"]
        assert not rf.review_path(repo, "M1.1", "sol").exists()
    else:   # the same earlier answer, last: filed
        assert run["outcome"] == "recorded", run["reason"]
