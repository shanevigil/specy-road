"""``specy-road review delegate``: a rostered reviewer run on a fake claude-code harness (M11.7).

The fake (tests/review_delegate_helpers.py) answers as a launched reviewer does since M8.3: a final JSON object
specy-road files as the record.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests.helpers import script_subprocess_env
from tests.review_delegate_helpers import (CAPACITY, delegate_repo, delegate_roster, fake_calls, launches,
                                           set_steps, verdict_step)
from tests.review_repo_helpers import NODE, commit_file, git, make_review_repo, review_output
from tests.test_models_and_prompt import run_main

from specy_road.bundled_scripts import review_cli, role_prompt, role_prompt_cli
from specy_road.review_delegate import DelegateError, capacity_error, delegate, load_run
from specy_road.review_gate import evaluate_gate
from specy_road.review_model_check import MISMATCH_REASON
from specy_road.review_record_write import review_run_lock
from specy_road.reviewer_run_failure import save_run, run_path, turn_capacity_error
from specy_road.review_files import reviews_dir
from specy_road import review_files as rf
from specy_road.worker_adapters import ClaudeCode

def _run(*args: str) -> int:
    with pytest.raises(SystemExit) as e:
        review_cli.main(list(args))
    return e.value.code


def _delegate(repo: Path, *extra: str) -> int:
    return _run("review", "delegate", "M1.1", "--model", "opus", "--backoff", "0", *extra, "--repo-root", str(repo))


def _status(repo: Path, capsys) -> dict:
    capsys.readouterr()
    _run("handoff", "status", "M1.1", "--json", "--repo-root", str(repo))
    return json.loads(capsys.readouterr().out)["nodes"][0]


def test_success_builds_the_prompt_launches_and_records_the_session(tmp_path: Path, capsys) -> None:
    repo, spec = delegate_repo(tmp_path)
    set_steps(repo, spec, verdict_step(repo))
    assert _delegate(repo, "--json") == 0
    run = json.loads(capsys.readouterr().out)
    assert run["state"] == "complete" and run["harness"] == "claude-code" and run["reason"] is None
    assert run["commit"] == git(repo, "rev-parse", "HEAD") and len(run["attempts"]) == 1
    call = launches(fake_calls(spec), "--session-id")[-1]          # the fresh launch, by its argv
    assert call[1] == "--session-id" and run["session_id"] == call[2]   # chosen up front, reported back
    prompt = Path(call[0]).read_text()
    assert "## Your role: reviewer" in prompt and "# Review packet" in prompt
    assert load_run(repo, "M1.1", "opus")["session_id"] == call[2]
    assert Path(run["log"]).is_file()
    st = _status(repo, capsys)
    assert st["review_runs"][0]["state"] == "complete" and st["review_runs"][0]["current"]


def test_a_capacity_error_is_retried_with_backoff_and_resumes_the_session(tmp_path: Path) -> None:
    repo, spec = delegate_repo(tmp_path)
    set_steps(repo, spec, {"error": CAPACITY, "exit": 1}, {"error": CAPACITY, "exit": 1}, verdict_step(repo))
    waits: list[float] = []
    run = delegate(repo, "M1.1", "opus", retries=3, backoff=2.0, sleep=waits.append)
    assert run["state"] == "complete"
    assert [a["capacity"] for a in run["attempts"]] == [True, True, False]
    assert waits == [2.0, 4.0]                              # doubling, between attempts only
    sid, resumed = run["session_id"], launches(fake_calls(spec), "--resume")   # selected by argv, never counted
    assert any(c[c.index("--session-id") + 1] == sid for c in launches(fake_calls(spec), "--session-id"))
    assert resumed and all(c[c.index("--resume") + 1] == sid for c in resumed)   # each retry resumes that session
    assert all("Continue the review" in Path(c[0]).read_text() for c in resumed)


def test_a_retry_never_files_an_earlier_attempts_answer(tmp_path: Path) -> None:
    repo, spec = delegate_repo(tmp_path)
    # the first attempt says a valid verdict, then fails on capacity; only the last attempt's output is read
    first = {"say": json.dumps(verdict_step(repo)["answer"]), "error": CAPACITY, "exit": 1}
    set_steps(repo, spec, first, {"raw": "not a verdict"})
    run = delegate(repo, "M1.1", "opus", retries=1, backoff=0, sleep=lambda _s: None)
    assert [a["capacity"] for a in run["attempts"]] == [True, False] and run["outcome"] == "rerun"
    assert not (reviews_dir(repo, "M1.1") / "REVIEW-opus.md").exists()


def test_one_leafs_reviewer_runs_take_turns(tmp_path: Path) -> None:
    """Moved from tests/test_review_record_write.py (file limit): a refused launch writes none of the run's files."""
    repo, spec = delegate_repo(tmp_path)
    set_steps(repo, spec, verdict_step(repo))
    reviews = reviews_dir(repo, "M1.1")
    with review_run_lock(reviews), pytest.raises(DelegateError, match="another reviewer run of M1.1 is in progress"):
        delegate(repo, "M1.1", "opus", sleep=lambda s: None)
    assert delegate(repo, "M1.1", "opus", sleep=lambda s: None)["state"] == "complete"
    (reviews / "OUTPUT-opus.json").write_text("the active turn's answer")
    files = sorted(p for p in (repo / "work").rglob("*") if p.is_file())
    kept = {p: (p.stat().st_mtime_ns, p.read_bytes()) for p in files}   # prompts, run record, answer, schema, record
    with review_run_lock(reviews):   # as the active run holds it
        with pytest.raises(DelegateError, match="in progress"):
            delegate(repo, "M1.1", "opus", sleep=lambda s: None)
        assert run_main(role_prompt, "M1.1", "--model", "opus", "--role", "reviewer", "--channel", "cli", "--run",
                        "--repo-root", str(repo)) == 1
    assert sorted(p for p in (repo / "work").rglob("*") if p.is_file()) == files
    assert {p: (p.stat().st_mtime_ns, p.read_bytes()) for p in files} == kept


def test_capacity_retries_are_bounded_and_end_incomplete(tmp_path: Path, capsys) -> None:
    repo, spec = delegate_repo(tmp_path)
    set_steps(repo, spec, {"error": CAPACITY, "exit": 1})
    assert _delegate(repo, "--retries", "2") == 1
    run = load_run(repo, "M1.1", "opus")
    assert [a["capacity"] for a in run["attempts"]] == [True, True, True]
    assert run["state"] == "incomplete" and "capacity error after 3 attempt(s)" in run["reason"]
    assert "incomplete" in capsys.readouterr().out


def test_a_run_that_writes_no_record_is_incomplete_and_never_shows_the_old_verdict(tmp_path: Path, capsys) -> None:
    repo, spec = delegate_repo(tmp_path)
    set_steps(repo, spec, verdict_step(repo, "block"))
    assert _delegate(repo) == 0
    assert _status(repo, capsys)["state"] == "blocked"
    commit_file(repo, "src/a.py", "print('fixed')\n", "fix")       # the executor answers the block
    set_steps(repo, spec, {"error": CAPACITY, "exit": 1})
    assert _delegate(repo, "--retries", "0") == 1
    st = _status(repo, capsys)
    assert st["state"] != "blocked" and st["reviews"] == []          # the old block is not this commit's verdict
    assert any("REVIEW-opus.md: reviewed" in p and "re-review" in p for p in st["problems"])
    assert any("RUN-opus.json: opus's delegated review of this commit is incomplete" in p for p in st["problems"])
    capsys.readouterr()
    _run("handoff", "status", "M1.1", "--repo-root", str(repo))
    out = capsys.readouterr().out
    assert "RUN-opus.json: incomplete run by opus at " + git(repo, "rev-parse", "HEAD")[:12] in out
    _run("review", "list", "M1.1", "--repo-root", str(repo))
    out = capsys.readouterr().out
    assert "REVIEW-opus.md: block by opus" in out and "stale: not the commit under review" in out


def test_a_clean_exit_without_a_record_is_incomplete(tmp_path: Path) -> None:
    repo, spec = delegate_repo(tmp_path)
    set_steps(repo, spec, {})
    run = delegate(repo, "M1.1", "opus", sleep=lambda s: None)
    assert run["state"] == "incomplete" and run["outcome"] == "rerun"
    assert run["reason"] == "rerun requested: the final message is not one complete JSON object"
    assert len(run["attempts"]) == 1                                  # not a capacity error: no retry
    assert not (reviews_dir(repo, "M1.1") / "REVIEW-opus.md").exists()


def test_resume_continues_the_recorded_session(tmp_path: Path, capsys) -> None:
    repo, spec = delegate_repo(tmp_path)
    set_steps(repo, spec, {}, verdict_step(repo))
    assert _delegate(repo) == 1
    sid = load_run(repo, "M1.1", "opus")["session_id"]
    assert _delegate(repo, "--resume") == 0
    assert any(c[c.index("--resume") + 1] == sid for c in launches(fake_calls(spec), "--resume"))
    commit_file(repo, "src/a.py", "print('moved')\n", "moved")
    capsys.readouterr()
    assert _delegate(repo, "--resume") == 1                           # the session reviewed another commit
    assert "delegate without --resume" in capsys.readouterr().err


def test_an_unsafe_recorded_session_id_is_refused_without_a_traceback(tmp_path: Path, capsys) -> None:
    repo, spec = delegate_repo(tmp_path)
    save_run(run_path(repo, "M1.1", "opus"), {"harness": "claude-code", "commit": git(repo, "rev-parse", "HEAD"),
                                           "session_id": "x; rm -rf ~"})
    assert _delegate(repo, "--resume") == 1
    assert "has whitespace or shell metacharacters" in capsys.readouterr().err
    assert not spec.with_name("calls.json").exists()                     # nothing was launched


def test_refusals(tmp_path: Path, capsys) -> None:
    repo, _spec = delegate_repo(tmp_path)
    assert _run("review", "delegate", "M1.1", "--model", "nobody", "--repo-root", str(repo)) == 1
    assert "not in the roster" in capsys.readouterr().err
    # M21.21: a generic entry with no channels.cli is refused as `prompt --channel cli` refuses it, before --resume
    assert _run("review", "delegate", "M1.1", "--model", "plain", "--resume", "--repo-root", str(repo)) == 1
    assert "a generic reviewer needs a roster channels.cli" in capsys.readouterr().err
    (tmp_path / "gen").mkdir()
    repo, _spec = delegate_repo(tmp_path / "gen", delegate_roster("{fake} {prompt}").replace(
        "{id: plain, family: openai, roles: [reviewer]}", "{id: plain, family: openai, roles: [reviewer], "
        "channels: {cli: 'true {prompt}'}}"))
    assert _run("review", "delegate", "M1.1", "--model", "plain", "--resume", "--repo-root", str(repo)) == 2
    assert "unsupported by generic: resume" in capsys.readouterr().err

def test_a_chore_reviewer_keeps_its_launch_that_a_leaf_reviewer_is_refused(tmp_path: Path) -> None:
    """M21.21: the prompt launcher's reviewer checks are for roadmap reviews; a chore reviewer's launch is unchanged."""
    from specy_road.bundled_scripts import chore_cli   # noqa: PLC0415
    from tests.worker_repo_helpers import FAKE as WORKER_FAKE, worker_roster   # noqa: PLC0415

    script = tmp_path / "fake.py"
    script.write_text(WORKER_FAKE)
    repo = make_review_repo(tmp_path, orchestration=worker_roster(f"{sys.executable} {script} {{prompt}} --force"))
    (repo / ".gitignore").write_text("work/\n")
    git(repo, "add", ".gitignore")
    git(repo, "commit", "-qm", "ignore work")
    with pytest.raises(DelegateError, match="passes --force, which lets it write"):
        delegate(repo, "M1.1", "opus", sleep=lambda s: None)
    with pytest.raises(SystemExit) as e:
        chore_cli.main(["chore", "start", "fix-env", "--task", "Repair", "--zone", "src", "--review",
                        "--repo-root", str(repo)])
    assert not e.value.code
    run = delegate(repo, "fix-env", "opus", sleep=lambda s: None)
    assert run["attempts"] and run["attempts"][0].get("exit") == 0


@pytest.mark.parametrize("flag,value", [("--retries", "-1"), ("--retries", "1.5"), ("--backoff", "-1"),
                                        ("--backoff", "nan"), ("--backoff", "inf")])
def test_invalid_retry_controls_are_refused_before_any_launch(tmp_path: Path, capsys, flag: str, value: str) -> None:
    repo, spec = delegate_repo(tmp_path)
    set_steps(repo, spec, {"error": CAPACITY, "exit": 1})
    assert _run("review", "delegate", "M1.1", "--model", "opus", flag, value, "--repo-root", str(repo)) == 2
    assert f"argument {flag}" in capsys.readouterr().err
    assert not spec.with_name("calls.json").exists() and load_run(repo, "M1.1", "opus") is None


def test_zero_retries_still_makes_the_first_attempt_and_ends_incomplete(tmp_path: Path, capsys) -> None:
    repo, spec = delegate_repo(tmp_path)
    set_steps(repo, spec, {"error": CAPACITY, "exit": 1})
    assert _delegate(repo, "--retries", "0", "--json") == 1             # --backoff 0: no wait, no crash
    run = json.loads(capsys.readouterr().out)
    assert [a["capacity"] for a in run["attempts"]] == [True]
    assert run["state"] == "incomplete" and "capacity error after 1 attempt(s)" in run["reason"]


def test_bare_reviewer_launch_tracks_a_session_only_when_asked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    prompt = tmp_path / "p.md"
    prompt.write_text("x")
    plain = ClaudeCode().reviewer_launch(prompt, "m", tmp_path)
    assert "--output-format" not in plain.argv and plain.session_id is None
    fresh = ClaudeCode().reviewer_launch(prompt, "m", tmp_path, session=("s1", False))
    assert fresh.argv[3:8] == ["--bare", "--session-id", "s1", "--output-format", "stream-json"]
    assert fresh.session_id == "s1" and fresh.launch_mode == "bare"
    assert ClaudeCode().reviewer_launch(prompt, "m", tmp_path, session=("s1", True)).argv[4:6] == ["--resume", "s1"]


USAGE_LIMIT = "You've hit your usage limit for Opus. Try again after 11pm."


def test_handoff_policy_line_names_a_usage_limit_reviewer_failure(tmp_path: Path, capsys) -> None:
    repo, spec = delegate_repo(tmp_path)
    set_steps(repo, spec, {"error": USAGE_LIMIT, "exit": 1})
    assert _delegate(repo, "--retries", "0") == 1
    st = _status(repo, capsys)
    assert st["policy_met"] is False
    assert "reviewer failure (opus):" in st["policy"] and "usage limit" in st["policy"].lower()
    events = st["review_runs"][0]["events"]
    assert events[-1]["type"] == "reviewer-failure" and "usage limit" in events[-1]["error"].lower()


def test_successful_delegate_run_has_no_reviewer_failure_event(tmp_path: Path, capsys) -> None:
    repo, spec = delegate_repo(tmp_path)
    set_steps(repo, spec, verdict_step(repo))
    assert _delegate(repo) == 0
    run = _status(repo, capsys)["review_runs"][0]
    assert run["state"] == "complete" and not run.get("events")


def test_prompt_cli_channel_records_usage_limit_and_shows_it_on_the_gate_line(tmp_path: Path, capsys, monkeypatch) -> None:

    script = tmp_path / "fake_cli.py"
    script.write_text(
        "import sys\nprint(sys.argv[1], flush=True)\nprint(\"You've hit your usage limit\", file=sys.stderr)\n"
        "raise SystemExit(1)\n"
    )
    cli = f"{sys.executable} {{prompt}}"
    repo = make_review_repo(tmp_path, orchestration=delegate_roster(cli.replace("{prompt}", script.as_posix() + " {prompt}")))
    (reviews_dir(repo, "M1.1")).mkdir(parents=True, exist_ok=True)
    (reviews_dir(repo, "M1.1") / "PACKET.md").write_text("# Review packet\n\n**Commit under review:** HEAD\n")
    assert run_main(role_prompt, "M1.1", "--model", "opus", "--role", "reviewer", "--channel", "cli", "--run",
                    "--repo-root", str(repo)) == 1
    run = load_run(repo, "M1.1", "opus")
    assert run["source"] == "prompt-cli" and run["state"] == "incomplete"
    assert run["events"][-1]["type"] == "reviewer-failure" and "usage limit" in run["events"][-1]["error"].lower()
    st = _status(repo, capsys)
    assert "reviewer failure (opus):" in st["policy"] and "usage limit" in st["policy"].lower()


def test_capacity_error_reads_provider_wording() -> None:
    assert capacity_error(["ok", CAPACITY])
    assert capacity_error(["429 Too Many Requests"]) and capacity_error(["You've hit your usage limit"])
    assert capacity_error(["RESOURCE_EXHAUSTED"]) and not capacity_error(["SyntaxError: bad input"])


def test_review_text_that_mentions_capacity_is_not_a_capacity_error(tmp_path: Path) -> None:
    said = "Capacity and quota handling look right; the rate limit retry is covered (429 too)."
    assert not capacity_error([said.replace("rate limit retry", "retry").replace(" (429 too)", "")])
    assert turn_capacity_error([], [json.dumps({"type": "assistant", "text": said}), "done"]) is None
    assert turn_capacity_error([], [said, "Error: 429 Too Many Requests", ""]) == "Error: 429 Too Many Requests"
    repo, spec = delegate_repo(tmp_path)
    set_steps(repo, spec, {"say": said, "exit": 1})
    run = delegate(repo, "M1.1", "opus", retries=3, backoff=0, sleep=lambda _s: None)
    assert [a["capacity"] for a in run["attempts"]] == [False]   # no retry
    assert run["state"] == "incomplete" and "capacity" not in run["reason"]
    assert said not in run["events"][-1]["error"]


def test_prompt_cli_exception_closes_the_run_incomplete(tmp_path: Path, monkeypatch) -> None:

    repo, _spec = delegate_repo(tmp_path)

    def boom(*_a, **_k):
        raise RuntimeError("harness exploded")

    monkeypatch.setattr(role_prompt_cli, "run_reviewer_channel", boom)
    with pytest.raises(RuntimeError, match="harness exploded"):
        role_prompt.main(["M1.1", "--model", "opus", "--role", "reviewer", "--channel", "cli", "--run",
                          "--repo-root", str(repo)])
    run = load_run(repo, "M1.1", "opus")
    assert run["state"] == "incomplete" and run["ended_at"]
    assert run["events"][-1]["type"] == "reviewer-failure"
    assert "interrupted: harness exploded" in run["events"][-1]["error"]


def test_review_cli_module_main_prints_usage() -> None:
    done = subprocess.run([sys.executable, "-m", "specy_road.bundled_scripts.review_cli", "-h"],
                          capture_output=True, text=True, env=script_subprocess_env())
    assert done.returncode == 0
    assert "usage:" in done.stdout.lower()


# --- M15.31: delegated reviewer model id, refusal, and harness-reported model check -----------------------------

NO_PROFILE_ROSTER = ("version: 1\nroster:\n  - {id: human, family: human, roles: [coordinator, reviewer]}\n"
                     "  - {id: label-reviewer, family: anthropic, roles: [reviewer], harness: claude-code}\n")


def test_delegate_passes_the_roster_id_when_the_entry_has_no_profile(tmp_path: Path, monkeypatch) -> None:
    import os

    repo = make_review_repo(tmp_path, orchestration=NO_PROFILE_ROSTER)
    reviews_dir(repo, "M1.1").mkdir(parents=True, exist_ok=True)
    (reviews_dir(repo, "M1.1") / "PACKET.md").write_text("# Review packet\n\n**Commit under review:** HEAD\n")
    bin_dir, calls = tmp_path / "bin", tmp_path / "calls.jsonl"
    bin_dir.mkdir()
    fake_claude = """#!{python}
import json, sys
open({calls!r}, "a").write(json.dumps(sys.argv[1:]) + "\\n")
print(json.dumps({{"type": "system", "subtype": "init", "session_id": "s-1", "model": "label-reviewer"}}), flush=True)
ans = {answer!r}
print(json.dumps({{"type": "result", "subtype": "success", "result": ans, "session_id": "s-1"}}), flush=True)
"""
    answer = json.dumps(review_output(git(repo, "rev-parse", "HEAD"), model="label-reviewer"))
    (bin_dir / "claude").write_text(fake_claude.format(python=sys.executable, calls=str(calls), answer=answer))
    (bin_dir / "claude").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    assert delegate(repo, "M1.1", "label-reviewer", retries=0, backoff=0)["state"] == "complete"
    argv = json.loads(calls.read_text().splitlines()[0])
    assert argv[argv.index("--model") + 1] == "label-reviewer"


def test_delegate_records_model_mismatch_and_the_gate_excludes_the_approval(tmp_path: Path, capsys) -> None:
    repo, spec = delegate_repo(tmp_path)
    step = verdict_step(repo, model="opus")
    step["model"] = "gpt-5.6-sol"
    set_steps(repo, spec, step)
    assert _delegate(repo) == 0
    assert MISMATCH_REASON in capsys.readouterr().err
    run = load_run(repo, "M1.1", "opus")
    assert run["requested_model"] == "opus" and run["reported_model"] == "gpt-5.6-sol"
    rec = rf.load_review(rf.review_path(repo, "M1.1", "opus"), ["A1", "A2"])
    assert rec.ok and rec.data["harness_model"] == "gpt-5.6-sol" and rec.data["model_mismatch"] is True
    head = git(repo, "rev-parse", "HEAD")
    gate = evaluate_gate(repo, NODE, head)
    assert not gate.passed
    assert any(MISMATCH_REASON in why for _r, why in gate.ineligible)
    capsys.readouterr()
    _run("review", "list", "M1.1", "--repo-root", str(repo))
    assert MISMATCH_REASON in capsys.readouterr().out
