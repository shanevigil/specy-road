"""``specy-road review delegate``: a rostered reviewer run on a fake claude-code harness (M11.7)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests.helpers import script_subprocess_env
from tests.review_repo_helpers import commit_file, git, make_review_repo, review_text

from specy_road.bundled_scripts import review_cli
from specy_road.review_delegate import capacity_error, delegate, load_run
from specy_road.reviewer_run_failure import save_run, run_path, turn_capacity_error
from specy_road.review_files import reviews_dir
from specy_road.worker_adapters import ClaudeCode

# Each call takes the next step of the spec; the call's argv is appended to `calls`.
FAKE = '''
import json, os, sys
spec = json.loads(open(sys.argv[1]).read())
calls = json.loads(open(spec["calls"]).read()) if os.path.exists(spec["calls"]) else []
calls.append(sys.argv[2:])
open(spec["calls"], "w").write(json.dumps(calls))
step = spec["steps"][min(len(calls), len(spec["steps"])) - 1]
sid = sys.argv[-1]
print(json.dumps({"type": "system", "subtype": "init", "session_id": sid, "model": "fake"}), flush=True)
if step.get("write"):
    open(step["write"]["path"], "w").write(step["write"]["text"])
if step.get("say"):
    print(json.dumps({"type": "assistant", "session_id": sid,
                      "message": {"content": [{"type": "text", "text": step["say"]}]}}), flush=True)
if step.get("error"):
    print(json.dumps({"type": "result", "subtype": "error_during_execution", "is_error": True,
                      "result": step["error"], "session_id": sid}), flush=True)
else:
    print(json.dumps({"type": "result", "subtype": "success", "result": "filed", "session_id": sid}), flush=True)
sys.exit(step.get("exit", 0))
'''

CAPACITY = 'API Error: 529 {"type":"error","error":{"type":"overloaded_error","message":"Overloaded"}}'


def _roster(cli: str) -> str:
    return ("version: 1\nroster:\n  - {id: human, family: human, roles: [coordinator, reviewer]}\n"
            f"  - {{id: opus, family: anthropic, roles: [reviewer], harness: claude-code, channels: {{cli: '{cli}'}}}}\n"
            "  - {id: plain, family: openai, roles: [reviewer]}\n")


def _repo(tmp_path: Path) -> tuple[Path, Path]:
    script, spec = tmp_path / "fake.py", tmp_path / "spec.json"
    script.write_text(FAKE)
    repo = make_review_repo(tmp_path, orchestration=_roster(f"{sys.executable} {script} {spec} {{prompt}} {{session_flag}}"))
    (reviews_dir(repo, "M1.1")).mkdir(parents=True, exist_ok=True)
    (reviews_dir(repo, "M1.1") / "PACKET.md").write_text("# Review packet\n\n**Commit under review:** HEAD\n")
    return repo, spec


def _steps(repo: Path, spec: Path, *steps: dict) -> None:
    spec.write_text(json.dumps({"calls": str(spec.with_name("calls.json")), "steps": list(steps)}))


def _calls(spec: Path) -> list[list[str]]:
    return json.loads(spec.with_name("calls.json").read_text())


def _files_record(repo: Path, verdict: str = "approve") -> dict:
    """A step that files a valid REVIEW-opus.md for the commit under review."""
    text = review_text(git(repo, "rev-parse", "HEAD"), model="opus", verdict=verdict,
                       a1="pass" if verdict == "approve" else "fail")
    return {"write": {"path": str(reviews_dir(repo, "M1.1") / "REVIEW-opus.md"), "text": text}}


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
    repo, spec = _repo(tmp_path)
    _steps(repo, spec, _files_record(repo))
    assert _delegate(repo, "--json") == 0
    run = json.loads(capsys.readouterr().out)
    assert run["state"] == "complete" and run["harness"] == "claude-code" and run["reason"] is None
    assert run["commit"] == git(repo, "rev-parse", "HEAD") and len(run["attempts"]) == 1
    (call,) = _calls(spec)
    assert call[1] == "--session-id" and run["session_id"] == call[2]   # chosen up front, reported back
    prompt = Path(call[0]).read_text()
    assert "## Your role: reviewer" in prompt and "# Review packet" in prompt
    assert load_run(repo, "M1.1", "opus")["session_id"] == call[2]
    assert Path(run["log"]).is_file()
    st = _status(repo, capsys)
    assert st["review_runs"][0]["state"] == "complete" and st["review_runs"][0]["current"]


def test_a_capacity_error_is_retried_with_backoff_and_resumes_the_session(tmp_path: Path) -> None:
    repo, spec = _repo(tmp_path)
    _steps(repo, spec, {"error": CAPACITY, "exit": 1}, {"error": CAPACITY, "exit": 1}, _files_record(repo))
    waits: list[float] = []
    run = delegate(repo, "M1.1", "opus", retries=3, backoff=2.0, sleep=waits.append)
    assert run["state"] == "complete"
    assert [a["capacity"] for a in run["attempts"]] == [True, True, False]
    assert waits == [2.0, 4.0]                              # doubling, between attempts only
    first, second, third = _calls(spec)
    assert first[1] == "--session-id" and second[1:3] == third[1:3] == ["--resume", first[2]]
    assert "Continue the review" in Path(second[0]).read_text()


def test_capacity_retries_are_bounded_and_end_incomplete(tmp_path: Path, capsys) -> None:
    repo, spec = _repo(tmp_path)
    _steps(repo, spec, {"error": CAPACITY, "exit": 1})
    assert _delegate(repo, "--retries", "2") == 1
    assert len(_calls(spec)) == 3
    run = load_run(repo, "M1.1", "opus")
    assert run["state"] == "incomplete" and "capacity error after 3 attempt(s)" in run["reason"]
    assert "incomplete" in capsys.readouterr().out


def test_a_run_that_writes_no_record_is_incomplete_and_never_shows_the_old_verdict(tmp_path: Path, capsys) -> None:
    repo, spec = _repo(tmp_path)
    _steps(repo, spec, _files_record(repo, "block"))
    assert _delegate(repo) == 0
    assert _status(repo, capsys)["state"] == "blocked"
    commit_file(repo, "src/a.py", "print('fixed')\n", "fix")       # the executor answers the block
    _steps(repo, spec, {"error": CAPACITY, "exit": 1})
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
    repo, spec = _repo(tmp_path)
    _steps(repo, spec, {})
    run = delegate(repo, "M1.1", "opus", sleep=lambda s: None)
    assert run["state"] == "incomplete" and run["reason"] == "no REVIEW-opus.md was filed"
    assert len(run["attempts"]) == 1                                  # not a capacity error: no retry


def test_resume_continues_the_recorded_session(tmp_path: Path, capsys) -> None:
    repo, spec = _repo(tmp_path)
    _steps(repo, spec, {}, _files_record(repo))
    assert _delegate(repo) == 1
    sid = load_run(repo, "M1.1", "opus")["session_id"]
    assert _delegate(repo, "--resume") == 0
    assert _calls(spec)[1][1:3] == ["--resume", sid]
    commit_file(repo, "src/a.py", "print('moved')\n", "moved")
    capsys.readouterr()
    assert _delegate(repo, "--resume") == 1                           # the session reviewed another commit
    assert "delegate without --resume" in capsys.readouterr().err


def test_an_unsafe_recorded_session_id_is_refused_without_a_traceback(tmp_path: Path, capsys) -> None:
    repo, spec = _repo(tmp_path)
    save_run(run_path(repo, "M1.1", "opus"), {"harness": "claude-code", "commit": git(repo, "rev-parse", "HEAD"),
                                           "session_id": "x; rm -rf ~"})
    assert _delegate(repo, "--resume") == 1
    assert "has whitespace or shell metacharacters" in capsys.readouterr().err
    assert not spec.with_name("calls.json").exists()                     # nothing was launched


def test_refusals(tmp_path: Path, capsys) -> None:
    repo, _spec = _repo(tmp_path)
    assert _run("review", "delegate", "M1.1", "--model", "nobody", "--repo-root", str(repo)) == 1
    assert "not in the roster" in capsys.readouterr().err
    assert _run("review", "delegate", "M1.1", "--model", "plain", "--resume", "--repo-root", str(repo)) == 2
    assert "unsupported by generic: resume" in capsys.readouterr().err


@pytest.mark.parametrize("flag,value", [("--retries", "-1"), ("--retries", "1.5"), ("--backoff", "-1"),
                                        ("--backoff", "nan"), ("--backoff", "inf")])
def test_invalid_retry_controls_are_refused_before_any_launch(tmp_path: Path, capsys, flag: str, value: str) -> None:
    repo, spec = _repo(tmp_path)
    _steps(repo, spec, {"error": CAPACITY, "exit": 1})
    assert _run("review", "delegate", "M1.1", "--model", "opus", flag, value, "--repo-root", str(repo)) == 2
    assert f"argument {flag}" in capsys.readouterr().err
    assert not spec.with_name("calls.json").exists() and load_run(repo, "M1.1", "opus") is None


def test_zero_retries_still_makes_the_first_attempt_and_ends_incomplete(tmp_path: Path, capsys) -> None:
    repo, spec = _repo(tmp_path)
    _steps(repo, spec, {"error": CAPACITY, "exit": 1})
    assert _delegate(repo, "--retries", "0", "--json") == 1             # --backoff 0: no wait, no crash
    run = json.loads(capsys.readouterr().out)
    assert len(_calls(spec)) == 1 and [a["capacity"] for a in run["attempts"]] == [True]
    assert run["state"] == "incomplete" and "capacity error after 1 attempt(s)" in run["reason"]


def test_bare_reviewer_launch_tracks_a_session_only_when_asked(tmp_path: Path) -> None:
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
    repo, spec = _repo(tmp_path)
    _steps(repo, spec, {"error": USAGE_LIMIT, "exit": 1})
    assert _delegate(repo, "--retries", "0") == 1
    st = _status(repo, capsys)
    assert st["policy_met"] is False
    assert "reviewer failure (opus):" in st["policy"] and "usage limit" in st["policy"].lower()
    events = st["review_runs"][0]["events"]
    assert events[-1]["type"] == "reviewer-failure" and "usage limit" in events[-1]["error"].lower()


def test_successful_delegate_run_has_no_reviewer_failure_event(tmp_path: Path, capsys) -> None:
    repo, spec = _repo(tmp_path)
    _steps(repo, spec, _files_record(repo))
    assert _delegate(repo) == 0
    run = _status(repo, capsys)["review_runs"][0]
    assert run["state"] == "complete" and not run.get("events")


def test_prompt_cli_channel_records_usage_limit_and_shows_it_on_the_gate_line(tmp_path: Path, capsys, monkeypatch) -> None:
    from specy_road.bundled_scripts import role_prompt
    from tests.test_models_and_prompt import run_main

    script = tmp_path / "fake_cli.py"
    script.write_text(
        "import sys\nprint(sys.argv[1], flush=True)\nprint(\"You've hit your usage limit\", file=sys.stderr)\n"
        "raise SystemExit(1)\n"
    )
    cli = f"{sys.executable} {{prompt}}"
    repo = make_review_repo(tmp_path, orchestration=_roster(cli.replace("{prompt}", script.as_posix() + " {prompt}")))
    (reviews_dir(repo, "M1.1")).mkdir(parents=True, exist_ok=True)
    (reviews_dir(repo, "M1.1") / "PACKET.md").write_text("# Review packet\n\n**Commit under review:** HEAD\n")
    assert run_main(role_prompt, "M1.1", "--model", "opus", "--role", "reviewer", "--channel", "cli",
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
    repo, spec = _repo(tmp_path)
    _steps(repo, spec, {"say": said, "exit": 1})
    run = delegate(repo, "M1.1", "opus", retries=3, backoff=0, sleep=lambda _s: None)
    assert len(_calls(spec)) == 1 and [a["capacity"] for a in run["attempts"]] == [False]   # no retry
    assert run["state"] == "incomplete" and "capacity" not in run["reason"]
    assert said not in run["events"][-1]["error"]


def test_prompt_cli_exception_closes_the_run_incomplete(tmp_path: Path, monkeypatch) -> None:
    from specy_road.bundled_scripts import role_prompt

    repo, _spec = _repo(tmp_path)

    def boom(*_a, **_k):
        raise RuntimeError("harness exploded")

    monkeypatch.setattr(role_prompt, "run_cli_channel", boom)
    with pytest.raises(RuntimeError, match="harness exploded"):
        role_prompt.main(["M1.1", "--model", "opus", "--role", "reviewer", "--channel", "cli",
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
