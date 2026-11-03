"""M8.2: hardened launches per harness, the retry watchdog, paused_by_limit, and the post-run check.

Fake harness binaries on PATH record the argv and environment the wrapper really ran them with and replay
the streams in ``fixtures/worker_turn_check/streams.json`` (constructed from the documented shapes; see its note).
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from tests.review_repo_helpers import git, make_review_repo

from specy_road import worker_adapter_codex as codex
from specy_road import worker_adapter_cursor as cursor
from specy_road import worker_adapters as wa
from specy_road import worker_ops_message as wom
from specy_road import worker_reconcile as wrc
from specy_road import worker_runner as wr
from specy_road import worker_state as ws
from specy_road import worker_turn_check as tc
from specy_road.worker_adapter_claude import EXECUTOR_TOOLS
from specy_road.worker_adapter_cursor import create_chat as real_create_chat   # before conftest stubs it
from specy_road.worker_adapter_parsers import limit_detail

STREAMS = json.loads((Path(__file__).parent / "fixtures/worker_turn_check/streams.json").read_text())

FAKE = '''
import json, os, subprocess, sys, time
spec_path = os.environ["FAKE_HARNESS_SPEC"]
spec = json.load(open(spec_path))
stdin = sys.stdin.read()
with open(spec_path + ".calls", "a") as f:
    f.write(json.dumps({"argv": sys.argv[1:], "codex_home": os.environ.get("CODEX_HOME"), "stdin": stdin}) + "\\n")
if sys.argv[1:2] == ["create-chat"]:
    print(spec.get("chat", ""), flush=True)
    sys.exit(spec.get("chat_exit", 0))
for cmd in spec.get("run", []):
    subprocess.run(cmd, shell=True, check=True, capture_output=True)
for d in spec.get("lines", []):
    print(json.dumps(d), flush=True)
time.sleep(spec.get("sleep", 0))
sys.exit(spec.get("exit", 0))
'''


def _harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str, **spec) -> Path:
    """Install a fake ``name`` binary first on PATH; returns its spec file (``.calls`` beside it records runs)."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    exe = bin_dir / name
    exe.write_text(f"#!{sys.executable}\n{FAKE}")
    exe.chmod(0o755)
    path = tmp_path / f"{name}.spec.json"
    path.write_text(json.dumps(spec))
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_HARNESS_SPEC", str(path))
    return path


def _calls(spec: Path) -> list[dict]:
    calls = Path(f"{spec}.calls")
    return [json.loads(x) for x in calls.read_text().splitlines()] if calls.is_file() else []


def _respec(spec: Path, **kw) -> None:
    spec.write_text(json.dumps(kw))


def _prompt(tmp_path: Path) -> Path:
    p = tmp_path / "prompt.md"
    p.write_text("do the leaf")
    return p


def _events(repo: Path, wid: str, type_: str) -> list[ws.WorkerEvent]:
    return [e for e in ws.events_since(repo, wid) if e.type == type_]


def _findings(repo: Path, wid: str) -> set[str]:
    return {f["kind"] for f in _events(repo, wid, "post_run_check")[-1].detail["findings"]}


# --- A1: Claude Code --------------------------------------------------------------------------------------


def test_claude_launch_and_resume_pass_mode_tools_and_no_prompts_and_a_denial_flags_the_worker(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = make_review_repo(tmp_path)
    spec = _harness(tmp_path, monkeypatch, "claude", lines=STREAMS["claude_denied"])
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo, branch="feature/rm-thing")
    adapter = wa.adapter_for("claude-code")
    assert wr.run(repo, rec.worker_id, adapter.launch(_prompt(tmp_path), repo, "claude-opus-5-5", None)) == 0
    argv = _calls(spec)[0]["argv"]
    resumed = adapter.resume("sid", _prompt(tmp_path), repo, "claude-opus-5-5", None).argv[1:]
    for args in (argv, resumed):   # the resume keeps the launch's permissions
        i = args.index("--allowedTools")
        assert args[i + 1] == EXECUTOR_TOOLS == "Read,Edit,Write,Glob,Grep,Bash"
        assert args[i + 2:i + 6] == ["--permission-prompts", "none", "--permission-mode", "acceptEdits"]
        assert args[-1] == wa.STDIN_INSTRUCTION and "-w" not in args and "--worktree" not in args
    assert _calls(spec)[0]["stdin"] == "do the leaf"
    # Exit 0 and subtype success, yet the denial is an event and a finding that flags the worker.
    rec = ws.load_record(repo, rec.worker_id)
    [denied] = _events(repo, rec.worker_id, "permission_denied")
    assert denied.detail == {"tool_name": "Bash", "tool_input": {"command": "git push origin HEAD"}, "tool_use_id": "toolu_01"}
    assert rec.state == "idle" and tc.FLAG_POST_RUN in rec.flags and _findings(repo, rec.worker_id) == {"permission_denied"}
    [shown] = [w for w in wrc.sync(repo, ack=True) if w["worker_id"] == rec.worker_id]
    assert tc.FLAG_POST_RUN in shown["flags"] and "post_run_check" in [e["type"] for e in shown["events"]]
    # The next clean turn clears the flag and records no check event.
    _respec(spec, lines=STREAMS["claude_clean"])
    wr.run(repo, rec.worker_id, adapter.resume("sid", _prompt(tmp_path), repo, "m", None))
    assert tc.FLAG_POST_RUN not in ws.load_record(repo, rec.worker_id).flags
    assert len(_events(repo, rec.worker_id, "post_run_check")) == 1


def test_a_limit_reported_as_success_pauses_the_worker_and_resume_waits_for_the_reset(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = make_review_repo(tmp_path)
    _harness(tmp_path, monkeypatch, "claude", lines=STREAMS["claude_limit_as_success"])
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo, branch="feature/rm-thing")
    assert wr.run(repo, rec.worker_id, wa.adapter_for("claude-code").launch(_prompt(tmp_path), repo, "m", None)) == 0
    rec = ws.load_record(repo, rec.worker_id)
    assert rec.state == tc.PAUSED_BY_LIMIT and rec.lease["holder"] == "broker"   # keeps its slot, like idle
    reset = datetime.fromisoformat(rec.limit_reset_at)
    assert reset.astimezone(timezone(timedelta(hours=1))).strftime("%H:%M") == "01:20"   # Europe/Amsterdam in November
    [limited] = _events(repo, rec.worker_id, "usage_limited")
    assert limited.detail["reset_at"] == rec.limit_reset_at and "session limit" in limited.detail["evidence"]
    assert "usage_limit" in _findings(repo, rec.worker_id)
    with pytest.raises(ws.WorkerError, match="paused by a usage limit until"):
        wom.message(repo, rec.worker_id, "continue")
    tc.limit_gate(rec, now=reset + timedelta(seconds=1))   # after the reset: no refusal
    with pytest.raises(ws.WorkerError):
        tc.limit_gate(rec, now=reset - timedelta(seconds=1))
    assert ws.load_record(repo, rec.worker_id).state == tc.PAUSED_BY_LIMIT   # the refusal changed nothing


def test_the_retry_watchdog_stops_a_harness_retrying_a_rate_limit_past_the_cap(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = make_review_repo(tmp_path)
    _harness(tmp_path, monkeypatch, "claude", lines=STREAMS["claude_rate_limit_retries"], sleep=60)
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo, branch="feature/rm-thing")
    started = time.monotonic()
    code = wr.run(repo, rec.worker_id, wa.adapter_for("claude-code").launch(_prompt(tmp_path), repo, "m", None))
    assert code != 0 and time.monotonic() - started < 30   # 900 s announced > the 600 s cap: stopped, not waited out
    rec = ws.load_record(repo, rec.worker_id)
    assert rec.state == tc.PAUSED_BY_LIMIT and rec.limit_reset_at
    assert len(_events(repo, rec.worker_id, "api_retry")) == 3
    [stop] = [e for e in _events(repo, rec.worker_id, "usage_limited") if e.source == "system"]
    assert stop.detail["source"] == "watchdog" and "600s cap" in stop.detail["evidence"]
    assert {"api_retry", "usage_limit"} <= _findings(repo, rec.worker_id)


def test_retries_a_finished_turn_followed_are_a_finding_not_a_pause(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo, branch="feature/rm-thing")
    watch = tc.TurnWatch(repo, rec)
    claude = wa.adapter_for("claude-code")
    for line in (STREAMS["claude_rate_limit_retries"][1], STREAMS["claude_clean"][1]):
        for parsed in claude.parse_events(json.dumps(line), wa.Launch(["claude"])):
            watch.observe(parsed)
    assert watch.pending is None and watch.limit is None and watch.rate_wait == 300
    assert not tc.close_turn(repo, rec, watch)
    assert _findings(repo, rec.worker_id) == {"api_retry"}


# --- A2: Codex and Cursor ---------------------------------------------------------------------------------


def test_codex_runs_exec_json_workspace_write_memories_off_in_a_profile_codex_home(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = make_review_repo(tmp_path)
    user_home = tmp_path / "user-codex"
    user_home.mkdir()
    (user_home / "auth.json").write_text("{}")
    monkeypatch.setenv("CODEX_HOME", str(user_home))   # the user's own home: only its auth.json is linked
    spec = _harness(tmp_path, monkeypatch, "codex", lines=STREAMS["codex_try_again"], exit=1)
    rec = ws.create_record(repo, "M1.1", "codex", "sol", repo, branch="feature/rm-thing")
    before = datetime.now(timezone.utc)
    assert wr.run(repo, rec.worker_id, wa.adapter_for("codex").launch(_prompt(tmp_path), repo, "gpt-6.1-sol", None)) == 1
    [call] = _calls(spec)
    home = codex.codex_homes() / "gpt-6.1-sol"
    assert call["argv"][:2] == ["exec", "--json"] and call["argv"][-1] == "-" and call["stdin"] == "do the leaf"
    for pair in ("sandbox_mode=workspace-write", "approval_policy=never", "features.memories=false",
                 "memories.use_memories=false", "memories.generate_memories=false"):
        assert call["argv"][call["argv"].index(pair) - 1] == "-c"
    assert call["codex_home"] == str(home) and (home / "auth.json").resolve() == (user_home / "auth.json").resolve()
    # The failure's "try again in" time pauses the worker, exit 1 notwithstanding.
    rec = ws.load_record(repo, rec.worker_id)
    assert rec.state == tc.PAUSED_BY_LIMIT
    assert timedelta(minutes=89) < datetime.fromisoformat(rec.limit_reset_at) - before < timedelta(minutes=91)
    # Resume and hand-off find the thread in the profile's home, with the same memory switches.
    thread = STREAMS["codex_try_again"][0]["thread_id"]
    rollout = home / "sessions/2026/11/03" / f"rollout-2026-11-03T01-00-00-{thread}.jsonl"
    rollout.parent.mkdir(parents=True)
    rollout.write_text("{}\n")
    resumed = wa.adapter_for("codex").resume(thread, _prompt(tmp_path), repo, "other-model", None)
    assert resumed.env == {"CODEX_HOME": str(home)} and "memories.generate_memories=false" in resumed.argv
    assert wa.adapter_for("codex").human_resume(thread, repo) == ["env", f"CODEX_HOME={home}", "codex", "resume", thread]


def test_cursor_creates_the_chat_first_passes_force_trust_and_never_w(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cursor, "create_chat", real_create_chat)
    spec = _harness(tmp_path, monkeypatch, "agent", chat="chat-7f3a")
    launch = wa.adapter_for("cursor").launch(_prompt(tmp_path), tmp_path, "composer-2.5", None)
    assert _calls(spec)[0]["argv"] == ["create-chat"]
    assert launch.session_id == "chat-7f3a" and launch.argv[:4] == ["agent", "-p", "--resume", "chat-7f3a"]
    assert "--force" in launch.argv and "--trust" in launch.argv and launch.argv[-1] == "do the leaf"
    assert not {"-w", "--worktree"} & set(launch.argv)
    for cli in ("agent -p -w --force {prompt}", "agent -p --worktree=x {prompt}"):
        with pytest.raises(wa.Unsupported, match="never pass -w"):
            wa.adapter_for("cursor").launch(_prompt(tmp_path), tmp_path, "m", cli)
    _respec(spec, chat="", chat_exit=1)
    with pytest.raises(wa.Unsupported, match="create-chat"):
        wa.adapter_for("cursor").launch(_prompt(tmp_path), tmp_path, "m", None)


# --- A3: the git half of the post-run check ---------------------------------------------------------------


def test_post_run_check_reports_branch_stash_porcelain_and_commits_outside_the_zones(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = make_review_repo(tmp_path)
    spec = _harness(tmp_path, monkeypatch, "claude", lines=STREAMS["claude_clean"], run=[
        "mkdir -p docs && echo y > docs/y.md && git add docs/y.md && git commit -qm outside",   # zone is src
        "echo changed >> src/a.py && git stash push -q -m m82-test",
        "git checkout -q -b elsewhere", "echo stray > stray.txt"])
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo, branch="feature/rm-thing")
    assert wr.run(repo, rec.worker_id, wa.adapter_for("claude-code").launch(_prompt(tmp_path), repo, "m", None)) == 0
    assert _findings(repo, rec.worker_id) == {"branch", "stash", "porcelain", "committed_outside_zones"}
    [check] = _events(repo, rec.worker_id, "post_run_check")
    by_kind = {f["kind"]: f for f in check.detail["findings"]}
    assert by_kind["porcelain"]["paths"] == ["stray.txt"] and by_kind["committed_outside_zones"]["paths"] == ["docs/y.md"]
    assert tc.FLAG_POST_RUN in ws.load_record(repo, rec.worker_id).flags
    # A turn that rewinds HEAD is reported as such.
    _respec(spec, lines=STREAMS["claude_clean"], run=["git reset -q --hard HEAD~1"])
    wr.run(repo, rec.worker_id, wa.adapter_for("claude-code").resume("sid", _prompt(tmp_path), repo, "m", None))
    assert _findings(repo, rec.worker_id) == {"head"}
    assert git(repo, "branch", "--show-current") == "elsewhere"


# --- parsing ------------------------------------------------------------------------------------------------


def test_limit_text_is_read_from_the_turn_never_the_exit_code() -> None:
    now = datetime(2026, 11, 3, 12, 0, tzinfo=timezone.utc)
    assert limit_detail("You've hit your usage limit. Try again in 2 days 3 hours.", failed=True, now=now)["reset_at"] \
        == (now + timedelta(days=2, hours=3)).isoformat()
    at = limit_detail("You've hit your usage limit. Try again at Nov 5th, 2026 3:05 PM.", failed=True, now=now)["reset_at"]
    assert at == datetime(2026, 11, 5, 15, 5).astimezone().astimezone(timezone.utc).isoformat()   # Codex prints local time
    assert limit_detail("Usage limit reached.", failed=True, now=now) == {"reset_at": None, "evidence": "Usage limit reached."}
    # A successful turn counts only with a stated reset: a reply about rate limiting is not a limit.
    assert limit_detail("I added rate limit handling to the client.", failed=False, now=now) is None
    assert limit_detail("boom", failed=True, now=now) is None
    out = wa.adapter_for("codex").parse_events(json.dumps(STREAMS["codex_try_again"][1]), wa.Launch(["codex"]))
    assert [p.type for p in out] == ["error", "usage_limited"] and out[1].detail["source"] == "codex turn.failed"
    claude = wa.adapter_for("claude-code").parse_events(json.dumps(STREAMS["claude_limit_as_success"][1]), wa.Launch(["claude"]))
    assert [p.type for p in claude] == ["turn_completed", "usage_limited"]
