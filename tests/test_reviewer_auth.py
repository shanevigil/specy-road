"""M15.2: a Claude Code reviewer is bare only with a key, explicit otherwise, refused when bare is forced."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from specy_road import review_files as rf
from specy_road.orchestrate_assign import Assignment
from specy_road.orchestrate_plan import stamp_reviewer_auth_notices
from specy_road.review_delegate import delegate
from specy_road.review_files import reviews_dir
from specy_road.claude_config import claude_config_dir
from specy_road.reviewer_auth import (
    auth_problem, bare_settings_argv, claude_reviewer_auth_notices, claude_reviewer_mode, launch_note,
    load_user_settings, reviewer_environment, user_settings_path,
)
from specy_road.worker_adapter_base import REVIEWER_DISALLOWED, REVIEWER_NO_WRITES, STDIN_INSTRUCTION
from specy_road.worker_adapter_claude import ClaudeCode
from tests.review_delegate_helpers import fake_reviewer_run
from tests.review_repo_helpers import claude_code_reviewer_repo, git, review_output
from tests.test_models_and_prompt import commit_profile, run_main
from tests.test_orchestrate_plan import plan_repo

SECRET = "sk-ant-m15-2-do-not-print"
HELPER = "echo sk-ant-HELPERSECRET"
FIXES = ("export ANTHROPIC_API_KEY", "configure apiKeyHelper", "let specy-road choose explicit mode")


def _isolate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, key: str | None = None) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    if key is not None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", key)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "empty-claude-config"))


def _force_bare(repo: Path) -> None:
    prof = repo / "model-profiles" / "anthropic-claude" / "claude-opus-5-5.md"
    prof.write_text(prof.read_text().replace("launch_mode: full", "launch_mode: bare", 1))
    commit_profile(repo)


@pytest.mark.parametrize("env,settings,mode", [
    ({}, {}, "explicit"),
    ({"ANTHROPIC_API_KEY": ""}, {}, "explicit"),
    ({"ANTHROPIC_API_KEY": "   "}, {}, "explicit"),
    ({"ANTHROPIC_API_KEY": SECRET}, {}, "bare"),
    ({}, {"apiKeyHelper": HELPER}, "bare"),
    ({}, {"apiKeyHelper": ""}, "explicit"),
    ({}, {"apiKeyHelper": "  "}, "explicit"),
    ({}, {"apiKeyHelper": ["nope"]}, "explicit"),
])
def test_bare_is_never_chosen_without_a_key_or_helper(env: dict, settings: dict, mode: str) -> None:
    assert claude_reviewer_mode(env, settings) == mode
    if mode == "bare":
        assert env.get("ANTHROPIC_API_KEY", "").strip() or (isinstance(settings.get("apiKeyHelper"), str)
                                                            and settings["apiKeyHelper"].strip())


def test_a_settings_dir_with_surrounding_whitespace_still_yields_its_helper(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``CLAUDE_CONFIG_DIR`` and ``HOME`` are the path as given, so a helper there is seen."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    account = tmp_path / " account "
    account.mkdir()
    (account / "settings.json").write_text(json.dumps({"apiKeyHelper": HELPER}))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(account))
    env = reviewer_environment()
    assert user_settings_path(env) == claude_config_dir() / "settings.json"
    assert claude_reviewer_mode(env, load_user_settings(env)) == "bare"
    assert bare_settings_argv(env) == ["--settings", str(account / "settings.json")]
    home = tmp_path / " home "
    (home / ".claude").mkdir(parents=True)
    (home / ".claude" / "settings.json").write_text(json.dumps({"apiKeyHelper": HELPER}))
    monkeypatch.delenv("CLAUDE_CONFIG_DIR")
    monkeypatch.setenv("HOME", str(home))
    env = reviewer_environment()
    assert user_settings_path(env) == claude_config_dir() / "settings.json"
    assert claude_reviewer_mode(env, load_user_settings(env)) == "bare"


def test_auth_problem_names_the_fixes_and_never_the_key() -> None:
    said = auth_problem("bare", {}, {})
    assert said is not None and all(fix in said for fix in FIXES)
    assert auth_problem("bare", {"ANTHROPIC_API_KEY": SECRET}, {}) is None
    assert auth_problem("explicit", {}, {}) is None
    assert SECRET not in said and SECRET not in launch_note("bare") and SECRET not in launch_note("explicit")
    assert "subscription login" in launch_note("bare") and "subscription login" in launch_note("explicit")


def test_each_mode_keeps_the_restrictions_and_explicit_argv_has_no_bare(tmp_path: Path) -> None:
    prompt, reviews = tmp_path / "p.md", tmp_path / "reviews"
    prompt.write_text("x")
    schema = tmp_path / "s.json"
    schema.write_text(json.dumps({"type": "object", "title": "specy-road reviewer output", "required": ["notes"]}))
    bare = ClaudeCode().reviewer_launch(prompt, "m", reviews, session=("s1", False), schema=schema, mode="bare")
    explicit = ClaudeCode().reviewer_launch(prompt, "m", reviews, session=("s1", False), schema=schema, mode="explicit")
    assert bare.launch_mode == "bare" and "--bare" in bare.argv
    assert explicit.launch_mode == "explicit" and "--bare" not in explicit.argv
    assert explicit.argv[explicit.argv.index("--setting-sources") + 1] == "user"
    assert "--strict-mcp-config" in explicit.argv and "--mcp-config" not in explicit.argv
    for launch in (bare, explicit):
        argv = launch.argv
        assert argv[:3] == ["claude", "-p", STDIN_INSTRUCTION]
        assert argv[argv.index("--disallowedTools") + 1:argv.index("--disallowedTools") + 1 + len(REVIEWER_NO_WRITES)
                    + len(REVIEWER_DISALLOWED)] == [*REVIEWER_NO_WRITES, *REVIEWER_DISALLOWED]
        assert json.loads(argv[argv.index("--json-schema") + 1])["title"] == "specy-road reviewer output"
        assert argv[argv.index("--add-dir") + 1] == str(reviews)
        assert SECRET not in json.dumps(argv)


def test_notices_are_one_per_forced_claude_reviewer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _isolate(monkeypatch, tmp_path)
    rows = [
        ("opus", {"harness": "claude-code", "roles": ["reviewer"]}, "bare"),
        ("fable", {"harness": "claude-code", "roles": ["reviewer"], "launch_mode": "bare"}, None),
        ("sol", {"harness": "codex", "roles": ["reviewer"]}, "bare"),
        ("wrapped", {"harness": "claude-code", "roles": ["reviewer"], "channels": {"cli": "cat"}}, "bare"),
        ("full", {"harness": "claude-code", "roles": ["reviewer"]}, "full"),
        ("exec", {"harness": "claude-code", "roles": ["executor"]}, "bare"),
    ]
    notes = claude_reviewer_auth_notices(rows)
    assert [n.split()[2] for n in notes] == ["opus", "fable"]
    assert all(all(fix in n for fix in FIXES) for n in notes)
    a1 = Assignment("M1", "public", "any", reviewers=["opus", "sol"])
    a2 = Assignment("M2", "public", "any", reviewers=["opus", "fable"])
    stamp_reviewer_auth_notices([[a1, a2]], notes)
    assert a1.notes == [notes[0]] and a2.notes == [notes[1]]   # each entry once, on the first leaf that staffs it
    monkeypatch.setenv("ANTHROPIC_API_KEY", SECRET)
    assert claude_reviewer_auth_notices(rows) == []
    (tmp_path / "empty-claude-config").mkdir()
    (tmp_path / "empty-claude-config" / "settings.json").write_text(json.dumps({"apiKeyHelper": HELPER}))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert claude_reviewer_auth_notices(rows) == []


def _fake_claude(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """A ``claude`` on ``PATH`` that records argv and exits. Git keeps the real ``Popen``."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "claude-calls.jsonl"
    (bin_dir / "claude").write_text(
        f"#!{sys.executable}\nimport json, os, sys\n"
        f"open({str(calls)!r}, 'a').write(json.dumps(sys.argv) + '\\n')\n"
        "sys.stdin.read()\n")
    (bin_dir / "claude").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    return calls


def _argv(calls: Path) -> list[list[str]]:
    if not calls.is_file():
        return []
    return [json.loads(line) for line in calls.read_text().splitlines() if line.strip()]


def _reviews(repo: Path) -> dict[str, bytes]:
    """File name to bytes for the leaf's reviews directory, so a refusal can be shown to change nothing."""
    d = reviews_dir(repo, "M1.1")
    return {p.name: p.read_bytes() for p in d.iterdir() if p.is_file()}


def test_delegate_explicit_without_a_key_records_the_mode_and_prints_the_note(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    _isolate(monkeypatch, tmp_path)
    repo = claude_code_reviewer_repo(tmp_path)
    recorded = _fake_claude(monkeypatch, tmp_path)
    run = delegate(repo, "M1.1", "opus", retries=0, backoff=0, sleep=lambda _s: None)
    argv = _argv(recorded)
    assert run["launch_mode"] == "explicit" and argv and "--bare" not in argv[0]
    assert "--setting-sources" in argv[0] and "--strict-mcp-config" in argv[0] and "--mcp-config" not in argv[0]
    err = capsys.readouterr().err
    assert "subscription login" in err and "explicit mode" in err


def test_delegate_bare_with_a_key_prints_the_note_and_hides_the_key(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    _isolate(monkeypatch, tmp_path, key=SECRET)
    repo = claude_code_reviewer_repo(tmp_path)
    recorded = _fake_claude(monkeypatch, tmp_path)
    run = delegate(repo, "M1.1", "opus", retries=0, backoff=0, sleep=lambda _s: None)
    argv = _argv(recorded)
    assert run["launch_mode"] == "bare" and argv and "--bare" in argv[0]
    err = capsys.readouterr().err
    blob = err + json.dumps(run) + recorded.read_text() + (reviews_dir(repo, "M1.1") / "RUN-opus.log").read_text()
    assert "subscription login" in err and "--bare" in err and SECRET not in blob


def test_forced_bare_without_a_key_refuses_before_a_run_record(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    from specy_road.bundled_scripts import review_cli, role_prompt

    _isolate(monkeypatch, tmp_path)
    repo = claude_code_reviewer_repo(tmp_path)
    _force_bare(repo)
    planted = reviews_dir(repo, "M1.1") / "RUN-opus.json"
    planted.write_text('{"planted": true}\n')
    before = _reviews(repo)
    recorded = _fake_claude(monkeypatch, tmp_path)
    assert run_main(review_cli, "review", "delegate", "M1.1", "--model", "opus", "--retries", "0",
                    "--repo-root", str(repo)) == 1
    err = capsys.readouterr().err
    assert all(fix in err for fix in FIXES) and _argv(recorded) == [] and _reviews(repo) == before
    prompt_calls = fake_reviewer_run(monkeypatch)
    assert run_main(role_prompt, "M1.1", "--model", "opus", "--role", "reviewer", "--channel", "cli",
                    "--repo-root", str(repo)) == 1
    err = capsys.readouterr().err
    assert all(fix in err for fix in FIXES) and _reviews(repo) == before
    assert not any(list(c.get("cmd", [])[:2]) == ["claude", "-p"] for c in prompt_calls)


def test_prompt_explicit_mode_is_recorded_and_a_helper_selects_bare_without_printing_it(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    from specy_road.bundled_scripts import role_prompt

    _isolate(monkeypatch, tmp_path)
    repo = claude_code_reviewer_repo(tmp_path)
    answer = review_output(git(repo, "rev-parse", "HEAD"), model="opus")
    calls = fake_reviewer_run(monkeypatch, [json.dumps({"type": "result", "subtype": "success", "result": "done",
                                                        "structured_output": answer})])
    assert run_main(role_prompt, "M1.1", "--model", "opus", "--role", "reviewer", "--channel", "cli",
                    "--repo-root", str(repo)) == 0
    argv = next(c["cmd"] for c in calls if list(c["cmd"][:2]) == ["claude", "-p"])
    assert "--bare" not in argv and "--setting-sources" in argv and "--mcp-config" not in argv
    run = json.loads((rf.reviews_dir(repo, "M1.1") / "RUN-opus.json").read_text())
    assert run["launch_mode"] == "explicit"
    assert rf.load_review(rf.review_path(repo, "M1.1", "opus"), ["A1", "A2"]).data["launch_mode"] == "explicit"
    capsys.readouterr()
    cfg = tmp_path / "empty-claude-config"
    cfg.mkdir()
    settings = cfg / "settings.json"
    settings.write_text(json.dumps({"apiKeyHelper": HELPER}))
    (tmp_path / "p.md").write_text("x")
    direct = ClaudeCode().reviewer_launch(tmp_path / "p.md", "m", tmp_path / "reviews", mode="bare")
    assert direct.argv[direct.argv.index("--settings") + 1] == str(settings)
    assert "--bare" in direct.argv and HELPER not in " ".join(direct.argv)
    calls.clear()
    assert run_main(role_prompt, "M1.1", "--model", "opus", "--role", "reviewer", "--channel", "cli",
                    "--repo-root", str(repo)) == 0
    argv = next(c["cmd"] for c in calls if list(c["cmd"][:2]) == ["claude", "-p"])
    captured = capsys.readouterr()
    log = (rf.reviews_dir(repo, "M1.1") / "RUN-opus.log").read_text()
    assert "--bare" in argv and argv[argv.index("--settings") + 1] == str(settings)
    assert HELPER not in " ".join(argv) and HELPER not in captured.err and HELPER not in captured.out
    assert HELPER not in log and "running:" in captured.err


def test_plan_prints_one_reviewer_auth_notice(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                             capsys: pytest.CaptureFixture[str]) -> None:
    from specy_road.bundled_scripts import orchestrate_cli

    _isolate(monkeypatch, tmp_path)
    roster = """version: 1
roster:
  - {id: human, family: human, roles: [coordinator, reviewer]}
  - id: opus
    family: anthropic
    harness: claude-code
    profile: model-profiles/anthropic-claude/claude-opus-5-5.md
    roles: [coordinator, executor, reviewer]
    class: senior
  - id: sol
    family: openai
    profile: model-profiles/openai-gpt/gpt-6.1-sol.md
    roles: [executor, reviewer]
  - id: flash
    family: google
    profile: model-profiles/google-gemini/gemini-3.8-flash.md
    roles: [executor]
    may_process: [public, internal]
policy:
  reviewers_required: 2
  reviewers_distinct_families: true
"""
    repo = plan_repo(tmp_path / "plan", roster=roster)
    prof = repo / "model-profiles" / "anthropic-claude" / "claude-opus-5-5.md"
    prof.write_text(prof.read_text().replace("launch_mode: full", "launch_mode: bare", 1))
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "force bare")
    assert run_main(orchestrate_cli, "orchestrate", "plan", "--today", "2026-11-01", "--repo-root", str(repo)) == 0
    out = capsys.readouterr().out
    assert out.count("reviewer auth:") == 1 and "opus" in out.split("reviewer auth:", 1)[1].splitlines()[0]
    assert all(fix in out for fix in FIXES)
    monkeypatch.setenv("ANTHROPIC_API_KEY", SECRET)
    assert run_main(orchestrate_cli, "orchestrate", "plan", "--today", "2026-11-01", "--repo-root", str(repo)) == 0
    again = capsys.readouterr().out
    assert "reviewer auth:" not in again and SECRET not in again
