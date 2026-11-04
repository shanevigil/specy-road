"""M11.62: what M8.2's post-run check leaves out: a limit only the Claude transcript names, a Codex
"try again at" reset, background tasks off for reviewers, and Codex overrides checked against the capture.

A fake harness on PATH records the environment it was started with and replays the lines in its spec;
the transcript and stream shapes are the documented ones M8.2's fixture uses (fixtures/worker_turn_check).
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tests.review_repo_helpers import make_review_repo

from specy_road import harness_facts as hf
from specy_road import worker_adapters as wa
from specy_road import worker_runner as wr
from specy_road import worker_state as ws
from specy_road import worker_turn_check as tc
from specy_road.bundled_scripts import refresh_profiles as rp
from specy_road.bundled_scripts.role_prompt import run_bare_reviewer
from specy_road.review_delegate import delegate
from specy_road.review_files import reviews_dir
from specy_road.worker_adapter_codex import CODEX_MEMORY_OFF

ENV_KEYS = ("CLAUDE_CODE_DISABLE_BACKGROUND_TASKS", "CLAUDE_CODE_DISABLE_AUTO_MEMORY")
FAKE = '''
import json, os, sys
spec = json.load(open(os.environ["FAKE_HARNESS_SPEC"]))
sys.stdin.read()
with open(os.environ["FAKE_HARNESS_SPEC"] + ".env", "a") as f:
    f.write(json.dumps({k: os.environ.get(k) for k in %r}) + "\\n")
for d in spec.get("lines", []):
    print(json.dumps(d), flush=True)
sys.exit(spec.get("exit", 0))
''' % (ENV_KEYS,)
SID = "3f2c9a7e-15b8-4d21-9c44-77aa10bd3e50"
INIT = {"type": "system", "subtype": "init", "session_id": SID, "model": "claude-opus-5-5"}
LIMIT = "You've hit your Claude Code session limit. Your limit resets 1:20am (Europe/Amsterdam)."


def _harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str, **spec) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    exe = bin_dir / name
    exe.write_text(f"#!{sys.executable}\n{FAKE}")
    exe.chmod(0o755)
    path = tmp_path / f"{name}.spec.json"
    path.write_text(json.dumps(spec))
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_HARNESS_SPEC", str(path))
    for key in ENV_KEYS:   # the caller's own switches (a run under Claude Code has them) must not leak in
        monkeypatch.delenv(key, raising=False)
    return path


def _envs(spec: Path) -> list[dict]:
    return [json.loads(x) for x in Path(f"{spec}.env").read_text().splitlines()]


def _prompt(tmp_path: Path) -> Path:
    p = tmp_path / "prompt.md"
    p.write_text("do the leaf; stop at a usage limit")   # limit wording in the prompt is never read as one
    return p


def _transcript(home: Path, sid: str, *entries: dict) -> None:
    """``~/.claude/projects/<project>/<session-id>.jsonl``: the prompt as a user entry, then ``entries``."""
    path = home / ".claude" / "projects" / "-tmp-some-worktree" / f"{sid}.jsonl"
    path.parent.mkdir(parents=True)
    user = {"type": "user", "message": {"role": "user", "content": "do the leaf; stop at a usage limit"}}
    path.write_text("".join(json.dumps(e) + "\n" for e in (user, *entries)))


def _run_claude(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, transcript: tuple[dict, ...] | None = None,
                **spec) -> tuple[Path, ws.WorkerRecord, Path]:
    """One executor turn on the fake ``claude``; ``transcript`` is written under ``$HOME`` for the launch's session."""
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    repo = make_review_repo(tmp_path)
    fake = _harness(tmp_path, monkeypatch, "claude", **spec)
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo, branch="feature/rm-thing")
    launch = wa.adapter_for("claude-code").launch(_prompt(tmp_path), repo, "claude-opus-5-5", None)
    if transcript is not None:
        _transcript(home, launch.session_id, *transcript)
    wr.run(repo, rec.worker_id, launch)
    return repo, ws.load_record(repo, rec.worker_id), fake


# --- A2: exit 1 with no result line: the transcript's last assistant message -----------------------------


def test_exit_1_with_no_result_line_reads_the_limit_from_the_session_transcript(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    api_error = {"type": "assistant", "isApiErrorMessage": True,
                 "message": {"role": "assistant", "content": [{"type": "text", "text": LIMIT}]}}
    repo, rec, _ = _run_claude(tmp_path, monkeypatch, (api_error,), lines=[INIT], exit=1)
    assert rec.state == tc.PAUSED_BY_LIMIT
    reset = datetime.fromisoformat(rec.limit_reset_at)
    assert reset.astimezone(timezone.utc).strftime("%H:%M") == "00:20"   # 1:20am Amsterdam in November
    [limited] = [e for e in ws.events_since(repo, rec.worker_id) if e.type == "usage_limited"]
    assert limited.detail["source"] == "claude-code transcript" and limited.detail["reset_at"] == rec.limit_reset_at


def test_exit_1_whose_transcript_names_no_limit_stays_failed_and_the_prompt_is_not_read(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # The transcript holds only the prompt, which mentions a usage limit.
    repo, rec, _ = _run_claude(tmp_path, monkeypatch, (), lines=[INIT], exit=1)
    assert rec.state == "failed" and rec.limit_reset_at is None
    assert not [e for e in ws.events_since(repo, rec.worker_id) if e.type == "usage_limited"]


def test_a_transcript_is_found_by_a_well_formed_session_id_only(tmp_path: Path) -> None:
    _transcript(tmp_path, SID, {"type": "assistant", "message": {"content": [{"type": "text", "text": LIMIT}]}})
    claude = wa.adapter_for("claude-code")
    assert claude.transcript_limit(SID, home=tmp_path).type == "usage_limited"
    for bad in (None, "", "*", "../x"):
        assert claude.transcript_limit(bad, home=tmp_path) is None


# --- A2: a Codex turn.failed that says "try again at <time>" ---------------------------------------------


def test_a_codex_try_again_at_failure_pauses_the_worker_until_that_local_time(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = make_review_repo(tmp_path)
    text = "You've hit your usage limit. Upgrade to Pro or try again at Nov 5th, 2099 3:05 PM."
    _harness(tmp_path, monkeypatch, "codex", exit=1, lines=[
        {"type": "thread.started", "thread_id": "0199a1b2-c3d4-7e5f-8a9b-0c1d2e3f4a5b"},
        {"type": "turn.failed", "error": {"message": text}}])
    rec = ws.create_record(repo, "M1.1", "codex", "sol", repo, branch="feature/rm-thing")
    assert wr.run(repo, rec.worker_id, wa.adapter_for("codex").launch(_prompt(tmp_path), repo, "gpt-6.1-sol", None)) == 1
    rec = ws.load_record(repo, rec.worker_id)
    assert rec.state == tc.PAUSED_BY_LIMIT
    assert datetime.fromisoformat(rec.limit_reset_at) == datetime(2099, 11, 5, 15, 5).astimezone()   # machine-local


# --- A3: background tasks off in the environment of every Claude Code launch ----------------------------


def test_executor_launches_get_both_switches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, _, fake = _run_claude(tmp_path, monkeypatch, lines=[INIT])
    assert _envs(fake) == [dict.fromkeys(ENV_KEYS, "1")]


def test_review_delegate_and_the_bare_reviewer_command_disable_background_tasks(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    roster = ("version: 1\nroster:\n  - {id: human, family: human, roles: [coordinator, reviewer]}\n"
              "  - {id: opus, family: anthropic, roles: [reviewer], harness: claude-code}\n")
    repo = make_review_repo(tmp_path, orchestration=roster)
    reviews = reviews_dir(repo, "M1.1")
    reviews.mkdir(parents=True, exist_ok=True)
    (reviews / "PACKET.md").write_text("# Review packet\n\n**Commit under review:** HEAD\n")
    fake = _harness(tmp_path, monkeypatch, "claude", lines=[INIT])
    delegate(repo, "M1.1", "opus", retries=0, backoff=0, sleep=lambda _s: None)
    assert run_bare_reviewer(None, _prompt(tmp_path), repo, "m", reviews, None) == 0
    # --bare already keeps auto memory off; background work would hold `claude -p` open up to 10 minutes idle.
    assert _envs(fake) == [{"CLAUDE_CODE_DISABLE_BACKGROUND_TASKS": "1", "CLAUDE_CODE_DISABLE_AUTO_MEMORY": None}] * 2


# --- A4: Codex memory overrides against the captured `codex features list` ------------------------------


def test_the_shipped_memory_overrides_are_all_listed_by_the_accepted_capture() -> None:
    capture = hf.read_capture(hf.bundled_captures_dir() / "codex")
    assert hf.unlisted_overrides(CODEX_MEMORY_OFF, capture) == []
    assert hf.unlisted_overrides(("-c", "features.no_such_feature=false", "-c", "memories.x=false"), capture) == [
        "features.no_such_feature"]


def test_refresh_profiles_check_fails_on_an_override_the_capture_does_not_list(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    captures = tmp_path / "captures"
    accepted = hf.read_capture(hf.bundled_captures_dir() / "codex")
    features = "".join(line + "\n" for line in accepted[hf.CODEX_FEATURES_FILE].splitlines()
                       if line.split()[:1] != ["memories"])
    hf.write_capture(captures / "codex", {**accepted, hf.CODEX_FEATURES_FILE: features})
    monkeypatch.setattr(hf, "bundled_captures_dir", lambda: captures)
    repo = tmp_path / "r"
    rp.refresh_profiles(repo)   # a fresh model-profiles/: no rendered drift, so only the overrides can fail
    with pytest.raises(SystemExit) as e:
        rp.main(["--check", "--repo-root", str(repo)])
    assert e.value.code == 1
    err = capsys.readouterr().err
    for key in ("features.memories", "memories.use_memories", "memories.generate_memories"):
        assert f"unlisted: codex -c {key}:" in err
    assert "rendered region(s) differ" not in err
