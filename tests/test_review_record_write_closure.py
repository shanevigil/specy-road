"""M8.3 A2/A3 regressions from Sol's block at 27d39730, through the public CLIs and ``delegate``.

F1 (the run lock overwritten in place) was withdrawn by the 2026-11-04 rescope: the lock is one of specy-road's run
files the tripwire leaves out (tests/test_review_record_write.py).
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

from tests.review_delegate_helpers import delegate_repo, delegate_roster, set_steps, verdict_step
from tests.review_repo_helpers import git, make_review_repo, review_output
from tests.test_models_and_prompt import run_main

from specy_road import review_files as rf
from specy_road.bundled_scripts import review_cli, role_prompt, role_prompt_cli
from specy_road.review_delegate import delegate, load_run
from specy_road.reviewer_run_failure import run_path, save_run


@pytest.mark.parametrize("state", ["rerun", "review_failure"])
def test_prompt_cli_keeps_a_failed_filing_incomplete_beside_an_older_record_of_the_commit(tmp_path: Path, capsys,
                                                                                          state: str) -> None:
    repo, spec = delegate_repo(tmp_path)
    second = ({"raw": "not a verdict"} if state == "rerun"
              else {**verdict_step(repo, "block"), "write": {"path": str(repo / "src" / "a.py"), "text": "x\n"}})
    set_steps(repo, spec, verdict_step(repo), second)
    assert delegate(repo, "M1.1", "opus", sleep=lambda _s: None)["outcome"] == "recorded"   # the older record
    older = rf.review_path(repo, "M1.1", "opus").read_bytes()
    assert run_main(role_prompt, "M1.1", "--model", "opus", "--role", "reviewer", "--channel", "cli", "--run",
                    "--repo-root", str(repo)) == 1
    run = load_run(repo, "M1.1", "opus")
    assert run["source"] == "prompt-cli" and run["state"] == "incomplete" and run["outcome"] == state
    said = "rerun requested" if state == "rerun" else "review failure"
    assert said in run["reason"] and run["events"][-1]["type"] == "reviewer-failure"
    assert said in run["events"][-1]["error"]
    assert rf.review_path(repo, "M1.1", "opus").read_bytes() == older       # untouched, and not this run's success
    assert said in capsys.readouterr().err


@pytest.mark.parametrize("how", ["preflight", "interrupt"])
def test_prompt_cli_that_sends_nothing_stays_incomplete_beside_an_older_record_of_the_commit(
        tmp_path: Path, monkeypatch, how: str) -> None:
    """Every close path of ``prompt --channel cli`` passes a filing outcome: a failed preflight (nothing sent) and an
    interrupt are incomplete with a reviewer-failure event, never complete on the strength of an older record."""
    stop = tmp_path / "stop"
    roster = delegate_roster("{fake} {prompt} {session_flag}").replace(
        "harness: claude-code,", f"harness: claude-code, preflight: 'test ! -e {stop}',")
    repo, spec = delegate_repo(tmp_path, roster)
    set_steps(repo, spec, verdict_step(repo))
    assert delegate(repo, "M1.1", "opus", sleep=lambda _s: None)["outcome"] == "recorded"   # the older record
    if how == "preflight":
        stop.write_text("")                                                    # the preflight now fails
    else:
        def interrupted(*_a, **_k):
            raise KeyboardInterrupt
        monkeypatch.setattr(role_prompt_cli, "run_reviewer_channel", interrupted)
    with pytest.raises((SystemExit, KeyboardInterrupt)) as e:
        role_prompt.main(["M1.1", "--model", "opus", "--role", "reviewer", "--channel", "cli", "--run",
                          "--repo-root", str(repo)])
    assert how == "interrupt" or e.value.code == 1
    run = load_run(repo, "M1.1", "opus")
    assert run["source"] == "prompt-cli" and run["state"] == "incomplete" and run["outcome"] == "rerun"
    said = "preflight failed" if how == "preflight" else "interrupted"
    assert said in run["reason"] and run["events"][-1]["type"] == "reviewer-failure"


FAKE_CODEX_TURNS = '''#!{python}
import json, os, sys
spec = json.loads(open(os.environ["FAKE_CODEX_SPEC"]).read())
argv = sys.argv[1:]
open(spec["calls"], "a").write(json.dumps(argv) + "\\n")
sys.stdin.read()
if "-o" in argv:   # a fresh turn: writes the verdict to -o, then fails on capacity, so specy-road resumes
    open(argv[argv.index("-o") + 1], "w").write(json.dumps(spec["answer"]))
    print(json.dumps({{"type": "thread.started", "thread_id": spec["sid"]}}))
    print("ERROR: 429 Too Many Requests", flush=True)
    sys.exit(1)
for text in spec["resume_texts"]:   # a resumed turn (no -o): these agent messages, then the turn ends
    print(json.dumps({{"type": "item.completed", "item": {{"type": "agent_message", "text": text}}}}))
print(json.dumps({{"type": "turn.completed", "usage": {{}}}}), flush=True)
'''


def _codex(tmp_path: Path, monkeypatch, **spec: object) -> tuple[Path, str, Path]:
    """``(repo, the commit, the calls file)`` for a codex reviewer ``sol`` run by :data:`FAKE_CODEX_TURNS`."""
    repo = make_review_repo(tmp_path, orchestration=(
        "version: 1\nroster:\n  - {id: human, family: human, roles: [coordinator, reviewer]}\n"
        "  - {id: sol, family: openai, roles: [reviewer], harness: codex}\n"))
    rf.reviews_dir(repo, "M1.1").mkdir(parents=True)
    (rf.reviews_dir(repo, "M1.1") / "PACKET.md").write_text("# Review packet\n")
    head, bin_dir, calls = git(repo, "rev-parse", "HEAD"), tmp_path / "bin", tmp_path / "codex-calls.jsonl"
    bin_dir.mkdir()
    (bin_dir / "codex").write_text(FAKE_CODEX_TURNS.format(python=sys.executable))
    (bin_dir / "codex").chmod(0o755)
    (tmp_path / "codex-spec.json").write_text(json.dumps({"calls": str(calls), "sid": str(uuid.uuid4()),
                                                          "answer": review_output(head, model="sol"), **spec}))
    monkeypatch.setenv("FAKE_CODEX_SPEC", str(tmp_path / "codex-spec.json"))
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")
    return repo, head, calls


@pytest.mark.parametrize("null_last", [True, False])
def test_a_codex_resume_whose_last_answer_event_has_no_text_is_a_rerun(tmp_path: Path, monkeypatch,
                                                                       null_last: bool) -> None:
    sid = str(uuid.uuid4())
    repo, head, calls = _codex(tmp_path, monkeypatch, resume_texts=["VERDICT", None] if null_last else ["VERDICT"])
    verdict = json.dumps(review_output(head, model="sol"))
    spec = json.loads((tmp_path / "codex-spec.json").read_text())
    spec["resume_texts"] = [verdict if t == "VERDICT" else t for t in spec["resume_texts"]]
    (tmp_path / "codex-spec.json").write_text(json.dumps(spec))
    save_run(run_path(repo, "M1.1", "sol"), {"node_id": "M1.1", "model": "sol", "harness": "codex", "commit": head,
                                             "session_id": sid, "state": "incomplete", "attempts": [], "events": []})
    run = delegate(repo, "M1.1", "sol", resume=True, sleep=lambda _s: None)
    argvs = [json.loads(line) for line in calls.read_text().splitlines()]
    resumed = [a for a in argvs if a[:2] == ["exec", "resume"]]
    assert resumed and all(sid in a and "-o" not in a for a in resumed)          # a resume: no -o file
    assert not [a for a in argvs if "-o" in a]                                    # no fresh turn, no retry
    # M21.42: a null answer after a clean exit gets exactly one repair launch, which resumes with the parse reason
    assert [a.get("repair", False) for a in run["attempts"]] == ([False, True] if null_last else [False])
    if null_last:
        assert run["outcome"] == "rerun" and run["state"] == "incomplete"
        assert "carries no answer" in run["reason"]
        assert run["refusal_kind"] == "parse"
        assert run["refusal"] in (repo / "work" / "prompt-M1.1-reviewer-sol-repair.md").read_text()
        assert not rf.review_path(repo, "M1.1", "sol").exists()
    else:   # the same earlier answer, last: filed
        assert run["outcome"] == "recorded", run["reason"]


def test_a_retried_codex_turn_never_files_the_failed_fresh_turns_answer_file(tmp_path: Path, monkeypatch) -> None:
    repo, _head, calls = _codex(tmp_path, monkeypatch, resume_texts=["not a verdict"])
    run = delegate(repo, "M1.1", "sol", retries=1, backoff=0, sleep=lambda _s: None)
    argvs = [json.loads(line) for line in calls.read_text().splitlines()]
    assert [a for a in argvs if "-o" in a] and [a for a in argvs if a[:2] == ["exec", "resume"]]   # by argv
    assert [a["capacity"] for a in run["attempts"]] == [True, False, False]
    assert [a.get("repair", False) for a in run["attempts"]] == [False, False, True]   # M21.42: one repair launch
    assert run["refusal_kind"] == "parse"
    assert run["refusal"] in (repo / "work" / "prompt-M1.1-reviewer-sol-repair.md").read_text()
    assert run["outcome"] == "rerun" and "the final message holds no JSON object" in run["reason"]
    assert not rf.review_path(repo, "M1.1", "sol").exists()
