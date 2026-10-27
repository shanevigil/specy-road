"""Harness adapters and the per-worker wrapper (slice 7b): commands, parsing, exit handling."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

from tests.review_repo_helpers import make_review_repo

from specy_road import worker_adapters as wa
from specy_road import worker_runner as wr
from specy_road import worker_state as ws

FAKE = '''
import json, sys
spec = json.loads(open(sys.argv[1]).read())
if spec.get("write"):
    open(spec["write"]["path"], "w").write(spec["write"]["text"])
for d in spec["lines"]:
    print(json.dumps(d), flush=True)
sys.exit(int(open(sys.argv[1]).read().count("FAIL") > 0))
'''


def _fake(tmp_path: Path, lines: list[dict], *, fail: bool = False, write: dict | None = None) -> tuple[Path, str]:
    """A harness stand-in: prints the given JSON lines; the prompt file carries them (and a file to write)."""
    script = tmp_path / "fake.py"
    script.write_text(FAKE)
    prompt = tmp_path / "prompt.json"
    prompt.write_text(json.dumps({"lines": lines, "note": "FAIL" if fail else "", "write": write}))
    return prompt, f"{sys.executable} {script} {{prompt}}"


def test_default_commands_follow_the_documented_cli_flags(tmp_path: Path) -> None:
    p = tmp_path / "p.md"
    p.write_text("do the thing")
    c = wa.adapter_for("claude-code").launch(p, tmp_path, "claude-opus-5-5", None)
    assert c.argv[:2] == ["claude", "-p"] and "--session-id" in c.argv and c.session_id in c.argv
    assert c.argv[-1] == wa.STDIN_INSTRUCTION and c.stdin == "do the thing" and "stream-json" in c.argv
    r = wa.adapter_for("claude-code").resume("sid", p, tmp_path, "m", None)
    assert r.argv[2:4] == ["--resume", "sid"] and r.stdin == "do the thing"
    x = wa.adapter_for("codex").launch(p, tmp_path, "gpt-6.1-sol", None)
    assert x.argv[:3] == ["codex", "exec", "--json"] and x.argv[-1] == "-" and x.stdin == "do the thing"
    assert wa.adapter_for("codex").resume("t1", p, tmp_path, "m", None).argv[:4] == ["codex", "exec", "resume", "--json"]
    u = wa.adapter_for("cursor").launch(p, tmp_path, "composer-2.5", None)
    assert u.argv[:2] == ["agent", "-p"] and "--force" in u.argv and "--workspace" in u.argv
    assert wa.adapter_for("claude-code").human_resume("sid", tmp_path) == ["claude", "--resume", "sid"]
    assert wa.adapter_for("codex").human_resume("t1", tmp_path) == ["codex", "resume", "t1"]
    assert wa.adapter_for("cursor").human_resume("c1", tmp_path) == ["agent", "--resume", "c1"]


def test_generic_needs_a_cli_and_custom_cli_overrides_any_harness(tmp_path: Path) -> None:
    p = tmp_path / "p.md"
    p.write_text("x")
    with pytest.raises(wa.Unsupported, match="channels.cli"):
        wa.adapter_for("generic").launch(p, tmp_path, "m", None)
    g = wa.adapter_for("generic").launch(p, tmp_path, "m", "mytool --file {prompt}")
    assert g.argv == ["sh", "-c", f"mytool --file {p}"]
    c = wa.adapter_for("claude-code").launch(p, tmp_path, "m", "wrapper {prompt}")
    assert c.argv[0] == "sh" and c.session_id is None
    # A custom command naming {session} gets a fresh id on launch, and keeps it.
    c = wa.adapter_for("claude-code").launch(p, tmp_path, "m", "wrapper --session-id {session} {prompt}")
    assert c.session_id and f"--session-id {c.session_id} " in c.argv[2]
    # The profiles' <prompt> form means the prompt text, quoted.
    g = wa.adapter_for("generic").launch(p, tmp_path, "m", 'tool "<prompt>"')
    assert g.argv[2] == "tool x"
    for h in ("generic",):
        with pytest.raises(wa.Unsupported):
            wa.adapter_for(h).resume("s", p, tmp_path, "m", None)
        with pytest.raises(wa.Unsupported):
            wa.adapter_for(h).human_resume("s", tmp_path)
    with pytest.raises(wa.Unsupported, match="unknown harness"):
        wa.adapter_for("copilot")
    for a in wa.ADAPTERS.values():
        assert a.caps.interrupt is False and a.caps.steer is False


def test_parsers_map_each_harness_output_to_events() -> None:
    cc = wa.adapter_for("claude-code")
    assert cc.parse('{"type":"system","subtype":"init","session_id":"s1","model":"opus"}').session_id == "s1"
    out = cc.parse('{"type":"assistant","session_id":"s1","message":{"content":[{"type":"text","text":"hi  there"}]}}')
    assert out.type == "output" and out.summary == "hi there"
    done = cc.parse('{"type":"result","subtype":"success","session_id":"s1","result":"ok","total_cost_usd":0.5}')
    assert done.type == "turn_completed" and done.detail == {"cost_usd": 0.5}
    assert cc.parse('{"type":"result","subtype":"error_max_turns","is_error":true}').type == "error"
    assert cc.parse("not json") is None and cc.parse('{"type":"user"}') is None
    cx = wa.adapter_for("codex")
    assert cx.parse('{"type":"thread.started","thread_id":"t1"}').session_id == "t1"
    assert cx.parse('{"type":"item.completed","item":{"type":"agent_message","text":"done"}}').summary == "done"
    assert cx.parse('{"type":"item.completed","item":{"type":"agent_message","text":""}}').summary == "(empty message)"
    assert cx.parse('{"type":"item.completed","item":{"type":"command_execution"}}').summary == "command_execution done"
    assert cx.parse('{"type":"turn.completed","usage":{"input_tokens":1}}').type == "turn_completed"
    assert cx.parse('{"type":"turn.failed","error":{"message":"boom"}}').type == "error"
    cu = wa.adapter_for("cursor")
    assert cu.parse('{"type":"system","subtype":"init","session_id":"c1"}').session_id == "c1"
    assert cu.parse('{"type":"tool_call","subtype":"started","session_id":"c1"}').summary == "tool call started"
    assert cu.parse('{"type":"result","subtype":"success","session_id":"c1","result":"fin"}').type == "turn_completed"
    assert wa.adapter_for("generic").parse("plain line").summary == "plain line"


def test_run_records_session_id_events_and_a_clean_exit(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    prompt, cli = _fake(tmp_path, [
        {"type": "system", "subtype": "init", "session_id": "s-42", "model": "opus"},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "working"}]}, "session_id": "s-42"},
        {"type": "result", "subtype": "success", "result": "all done", "session_id": "s-42"},
    ])
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    launch = wa.adapter_for("claude-code").launch(prompt, repo, "opus", cli)
    assert wr.run(repo, rec.worker_id, launch) == 0
    rec = ws.load_record(repo, rec.worker_id)
    assert rec.provider_session_id == "s-42" and rec.state == "idle" and rec.pid is None   # no READY file yet
    types = [e.type for e in ws.events_since(repo, rec.worker_id)]
    assert types == ["started", "started", "output", "turn_completed", "completion"]
    assert "working" in wr.log_path(repo, rec.worker_id).read_text()


def test_run_marks_completed_when_ready_exists_and_failed_on_nonzero_exit(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    from tests.review_repo_helpers import git
    d = ws.reviews_root(repo) / "M1.1"
    d.mkdir(parents=True)
    ready = {"path": str(d / "READY-sol.md"),      # written by the harness during the turn (review round 6, B3)
             "text": f"---\nnode_id: M1.1\nagent: sol\nbranch: feature/rm-thing\ncommit: {git(repo, 'rev-parse', 'HEAD')}\n"
                     f"base: {git(repo, 'rev-parse', 'HEAD')}\nchanged_paths: []\nverify: []\n---\n"}
    prompt, cli = _fake(tmp_path, [{"type": "thread.started", "thread_id": "t-9"}, {"type": "turn.completed"}], write=ready)
    rec = ws.create_record(repo, "M1.1", "codex", "sol", repo)
    wr.run(repo, rec.worker_id, wa.adapter_for("codex").launch(prompt, repo, "sol", cli))
    rec = ws.load_record(repo, rec.worker_id)
    assert rec.state == "completed" and rec.provider_session_id == "t-9"
    prompt2, cli2 = _fake(tmp_path, [{"type": "error", "message": "quota"}], fail=True)
    rec2 = ws.create_record(repo, "M1.2", "codex", "sol", repo)
    assert wr.run(repo, rec2.worker_id, wa.adapter_for("codex").launch(prompt2, repo, "sol", cli2)) == 1
    rec2 = ws.load_record(repo, rec2.worker_id)
    assert rec2.state == "failed"
    assert [e.type for e in ws.events_since(repo, rec2.worker_id)][-2:] == ["error", "error"]


def test_run_reports_a_missing_binary_as_failed(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    rec = ws.create_record(repo, "M1.1", "generic", "x", repo)
    assert wr.run(repo, rec.worker_id, wa.Launch(["/no/such/binary"])) == 127
    assert ws.load_record(repo, rec.worker_id).state == "failed"
    assert "cannot start" in ws.events_since(repo, rec.worker_id)[-1].summary


def test_spawn_returns_before_the_worker_ends_and_the_record_catches_up(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    prompt, cli = _fake(tmp_path, [{"type": "system", "subtype": "init", "session_id": "c-1"},
                                   {"type": "result", "subtype": "success", "result": "ok", "session_id": "c-1"}])
    rec = ws.create_record(repo, "M1.1", "cursor", "composer", repo)
    pid = wr.spawn(repo, rec, wa.adapter_for("cursor").launch(prompt, repo, "composer", cli))
    assert ws.load_record(repo, rec.worker_id).state == "running" and rec.pid == pid
    for _ in range(100):
        if not ws.load_record(repo, rec.worker_id).active or ws.load_record(repo, rec.worker_id).state == "idle":
            break
        time.sleep(0.1)
    final = ws.load_record(repo, rec.worker_id)
    assert final.state == "idle" and final.provider_session_id == "c-1" and not wr.pid_alive(final.pid)


def test_custom_cli_resume_needs_the_session_placeholder(tmp_path: Path) -> None:
    p = tmp_path / "p.md"
    p.write_text("x")
    cc = wa.adapter_for("claude-code")
    assert cc.resume("sid", p, tmp_path, "m", "wrapper {prompt}").argv[:2] == ["claude", "-p"]   # no {session}: default
    r = cc.resume("sid", p, tmp_path, "m", "wrapper {prompt} --resume {session}")
    assert r.argv[0] == "sh" and "--resume sid" in r.argv[2] and r.session_id == "sid"
