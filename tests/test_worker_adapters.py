"""Harness adapters and the per-worker wrapper (slice 7b): commands, parsing, exit handling."""

from __future__ import annotations

import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

import pytest

from tests.review_repo_helpers import make_review_repo, shipped_anthropic_opus_cli_yaml_line
from tests.test_models_and_prompt import commit_profile, make_profile_repo, run_main
from tests.test_worker_cli import run_worker_cli

from specy_road import worker_adapters as wa
from specy_road import worker_ops as ops
from specy_road import worker_reconcile as wrc
from specy_road import worker_runner as wr
from specy_road import worker_state as ws
from specy_road.bundled_scripts import role_prompt

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
    xr = wa.adapter_for("codex").resume("t1", p, tmp_path, "m", None)
    assert xr.argv[:4] == ["codex", "exec", "resume", "--json"] and xr.argv[-2:] == ["t1", "-"] and xr.stdin == "do the thing"
    # codex-cli 0.165: `exec` has no --ask-for-approval, and `exec resume` no --sandbox or -C either.
    for argv in (x.argv, xr.argv):
        assert "approval_policy=never" in argv and "sandbox_mode=workspace-write" in argv
        assert "--ask-for-approval" not in argv and "--sandbox" not in argv
    assert "-C" not in xr.argv
    u = wa.adapter_for("cursor").launch(p, tmp_path, "composer-2.5", None)
    assert u.argv[:2] == ["agent", "-p"] and "--force" in u.argv and "--workspace" in u.argv
    # a new worktree is an untrusted workspace: without --trust (or --force) `agent -p` exits 1
    ur = wa.adapter_for("cursor").resume("c1", p, tmp_path, "m", None)
    assert "--trust" in u.argv and "--trust" in ur.argv
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
    assert done.type == "turn_completed" and done.detail == {"cost_usd": 0.5, "message": "ok"}
    assert cc.parse('{"type":"result","subtype":"error_max_turns","is_error":true}').type == "error"
    assert cc.parse("not json") is None and cc.parse('{"type":"user"}') is None
    cx = wa.adapter_for("codex")
    assert cx.parse('{"type":"thread.started","thread_id":"t1"}').session_id == "t1"
    said = cx.parse('{"type":"item.completed","item":{"type":"agent_message","text":"done"}}')
    assert said.summary == "done" and said.detail == {"message": "done"}
    assert cx.parse('{"type":"item.completed","item":{"type":"agent_message","text":""}}').summary == "(empty message)"
    assert cx.parse('{"type":"item.completed","item":{"type":"command_execution"}}').summary == "command_execution done"
    assert cx.parse('{"type":"turn.completed","usage":{"input_tokens":1}}').type == "turn_completed"
    assert cx.parse('{"type":"turn.failed","error":{"message":"boom"}}').type == "error"
    cu = wa.adapter_for("cursor")
    assert cu.parse('{"type":"system","subtype":"init","session_id":"c1"}').session_id == "c1"
    assert cu.parse('{"type":"tool_call","subtype":"started","session_id":"c1"}').summary == "tool call started"
    assert cu.parse('{"type":"result","subtype":"success","session_id":"c1","result":"fin"}').type == "turn_completed"
    plain = wa.adapter_for("generic").parse("plain line")
    assert plain.summary == "plain line" and plain.detail == {"message": "plain line"}


RECORDED = json.loads((Path(__file__).parent / "fixtures/worker_usage/turn_end_lines.json").read_text())   # real, sanitized (M10.2)
CLAUDE_RESULT, CODEX_TURN, CURSOR_RESULT = (RECORDED[h]["lines"][i] for h, i in (("claude-code", 1), ("codex", -1), ("cursor", -1)))


def test_each_adapter_reports_turn_usage_in_one_shape() -> None:
    cc, cx, cu = (wa.adapter_for(h) for h in ("claude-code", "codex", "cursor"))
    assert cc.parse(json.dumps(CLAUDE_RESULT)).usage == {"input_tokens": 38 + 67090 + 1224204, "cached_input_tokens": 1224204,
        "output_tokens": 13258, "reasoning_tokens": 4703, "cost_usd": 1.0474079, "cost_is_estimate": True, "num_turns": 19,
        "harness_version": None, "session_cost_usd": 1.0474079}   # input counts cache reads and writes; the wrapper takes the delta
    assert cx.parse(json.dumps(CODEX_TURN)).usage == {"input_tokens": 14784, "cached_input_tokens": 12288, "output_tokens": 5,
        "reasoning_tokens": 0, "cost_usd": None, "cost_is_estimate": None, "num_turns": None, "harness_version": None}
    assert cu.parse(json.dumps(CURSOR_RESULT)).usage == {"input_tokens": 9323 + 4864, "cached_input_tokens": 4864, "output_tokens": 25,
        "reasoning_tokens": None, "cost_usd": None, "cost_is_estimate": None, "num_turns": None, "harness_version": None}
    assert set(cu.parse(json.dumps({**CURSOR_RESULT, "usage": None})).usage.values()) == {None}   # constructed: no usage → nulls
    w = cc.parse(json.dumps({**CLAUDE_RESULT, "usage": {"input_tokens": 12, "cache_creation_input_tokens": 3000}})).usage
    assert (w["input_tokens"], w["cached_input_tokens"], w["reasoning_tokens"]) == (3012, None, None)   # writes alone count
    bad = cc.parse(json.dumps({**CLAUDE_RESULT, "total_cost_usd": "1", "usage": {"output_tokens": "9", "input_tokens": True}}))
    assert {k: v for k, v in bad.usage.items() if v is not None} == {"num_turns": 19} and wa.adapter_for("generic").parse("x").usage is None


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
    assert types == ["started", "launched", "first_output", "started", "output", "turn_completed", "usage", "completion"]
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
    assert [e.type for e in ws.events_since(repo, rec2.worker_id)][-3:] == ["error", "usage", "error"]   # nulls: no usage


def test_run_reports_a_missing_binary_as_failed(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = make_review_repo(tmp_path)
    rec = ws.create_record(repo, "M1.1", "generic", "x", repo)
    assert wr.run(repo, rec.worker_id, wa.Launch(["/no/such/binary"])) == 127
    assert ws.load_record(repo, rec.worker_id).state == "failed"
    last = ws.events_since(repo, rec.worker_id)[-1]
    assert "cannot start" in last.summary and last.detail == {"exit": 127}
    assert [(e.type, set(e.detail.values())) for e in ws.events_since(repo, rec.worker_id)[-2:-1]] == [("usage", {None})]
    # The startup failure is the turn's end, so its ack is timed; the harness never launched or spoke.
    assert [d["worker_id"] for d in wrc.sync(repo, ack=True)] == [rec.worker_id]
    capsys.readouterr()
    assert run_worker_cli("worker", "timeline", rec.worker_id, "--json", "--repo-root", str(repo)) == 0
    phases = json.loads(capsys.readouterr().out)["phases"]
    assert isinstance(phases["end_to_acked"], float) and phases["end_to_acked"] >= 0
    assert phases["delegated_to_launched"] is None and phases["launched_to_first_output"] is None
    assert phases["first_output_to_end"] is None


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


# --- access.launch_mode (M10.4) -------------------------------------------------

FULL_INIT = {"type": "system", "subtype": "init", "session_id": "s1", "model": "opus", "claude_code_version": "2.1.300",
             "tools": ["Bash", "Read", "Edit", "Write", "Skill"], "mcp_servers": [{"name": "docs", "status": "connected"}],
             "plugins": [{"name": "lint", "path": "/p"}]}
BARE_INIT = {"type": "system", "subtype": "init", "session_id": "s1", "tools": ["Bash", "Read", "Edit"],
             "mcp_servers": [], "plugins": []}


def test_claude_passes_bare_only_when_the_profile_says_bare(tmp_path: Path) -> None:
    p = tmp_path / "p.md"
    p.write_text("x")
    cc = wa.adapter_for("claude-code")
    bare = cc.launch(p, tmp_path, "m", None, launch_mode="bare")
    assert "--bare" in bare.argv and bare.launch_mode == "bare"
    assert "--bare" in cc.resume("sid", p, tmp_path, "m", None, launch_mode="bare").argv
    for launch in (cc.launch(p, tmp_path, "m", None, launch_mode="full"), cc.launch(p, tmp_path, "m", None),
                   cc.resume("sid", p, tmp_path, "m", None, launch_mode="full")):
        assert "--bare" not in launch.argv and launch.launch_mode == "full"
    # A custom command is run as written; it only carries the mode for the init check.
    custom = cc.launch(p, tmp_path, "m", "wrapper {prompt}", launch_mode="bare")
    assert custom.argv == ["sh", "-c", f"wrapper {p}"] and custom.launch_mode == "bare"
    resumed = cc.resume("sid", p, tmp_path, "m", "wrapper {prompt} --resume {session}", launch_mode="bare")
    assert "--bare" not in resumed.argv[2] and resumed.launch_mode == "bare"


def test_claude_init_detail_reports_what_loaded_and_the_inferred_mode() -> None:
    cc = wa.adapter_for("claude-code")
    full = cc.parse(json.dumps(FULL_INIT))
    assert full.type == "started" and full.detail == {
        "tools": ["Bash", "Read", "Edit", "Write", "Skill"], "mcp_servers": ["docs"], "plugins": ["lint"],
        "version": "2.1.300", "inferred_mode": "full"}
    bare = cc.parse(json.dumps(BARE_INIT)).detail
    assert bare["inferred_mode"] == "bare" and "version" not in bare
    assert cc.parse(json.dumps({**BARE_INIT, "version": "2.1.301"})).detail["version"] == "2.1.301"
    # No tool list reported: nothing to infer from, so no mode and no mismatch.
    quiet = cc.parse('{"type":"system","subtype":"init","session_id":"s1"}').detail
    assert "inferred_mode" not in quiet


def test_claude_init_mismatch_adds_an_error_naming_both_modes(tmp_path: Path) -> None:
    cc = wa.adapter_for("claude-code")
    full, bare = wa.Launch(["claude"]), wa.Launch(["claude"], launch_mode="bare")
    assert [e.type for e in cc.parse_events(json.dumps(FULL_INIT), full)] == ["started"]
    assert [e.type for e in cc.parse_events(json.dumps(BARE_INIT), bare)] == ["started"]
    started, err = cc.parse_events(json.dumps(BARE_INIT), full)
    assert started.type == "started" and err.type == "error" and err.session_id == "s1"
    assert "bare mode" in err.summary and "launch_mode is full" in err.summary
    assert err.detail == {"inferred_mode": "bare", "launch_mode": "full"}
    assert [e.type for e in cc.parse_events(json.dumps(FULL_INIT), bare)] == ["started", "error"]
    assert cc.parse_events('{"type":"user"}', full) == []
    # Other harnesses never check the mode.
    assert [e.type for e in wa.adapter_for("cursor").parse_events(json.dumps(BARE_INIT), full)] == ["started"]


def test_the_wrapper_payload_carries_the_mode_and_records_the_mismatch(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    prompt, cli = _fake(tmp_path, [FULL_INIT, {"type": "result", "subtype": "success", "result": "ok", "session_id": "s1"}])
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    launch = wa.adapter_for("claude-code").launch(prompt, repo, "opus", cli, launch_mode="bare")
    payload = tmp_path / "payload.json"   # what `spawn` writes and `main` reads back
    payload.write_text(json.dumps({"launch": asdict(launch)}))
    with pytest.raises(SystemExit) as e:
        wr.main([str(repo), rec.worker_id, "tok", str(payload)])
    assert e.value.code == 0
    events = ws.events_since(repo, rec.worker_id)
    assert [x.type for x in events] == ["started", "launched", "first_output", "started", "error", "turn_completed",
                                        "usage", "completion"]
    mismatch = events[4]
    assert mismatch.detail == {"inferred_mode": "full", "launch_mode": "bare"}
    assert "exit" not in mismatch.detail   # not a turn end: the turn goes on
    assert ws.load_record(repo, rec.worker_id).provider_session_id == "s1"


# --- access.effort_by_role (M10.5) ----------------------------------------------

def test_default_claude_and_codex_commands_carry_the_effort_flag_and_cursor_none(tmp_path: Path) -> None:
    p = tmp_path / "p.md"
    p.write_text("x")
    cc, cx, cu = (wa.adapter_for(h) for h in ("claude-code", "codex", "cursor"))
    for launch in (cc.launch(p, tmp_path, "m", None, effort="medium"), cc.resume("sid", p, tmp_path, "m", None,
                                                                                  effort="medium")):
        i = launch.argv.index("--effort")
        assert launch.argv[i + 1] == "medium"
    for launch in (cx.launch(p, tmp_path, "m", None, effort="high"), cx.resume("t1", p, tmp_path, "m", None,
                                                                               effort="high")):
        i = launch.argv.index("model_reasoning_effort=high")
        assert launch.argv[i - 1] == "-c"
    assert cx.resume("t1", p, tmp_path, "m", None, effort="high").argv[-2:] == ["t1", "-"]   # still the last args
    no_effort = (cc.launch(p, tmp_path, "m", None), cc.resume("sid", p, tmp_path, "m", None),
                 cx.launch(p, tmp_path, "m", None), cx.resume("t1", p, tmp_path, "m", None))
    assert not any("--effort" in x.argv or any("model_reasoning_effort" in a for a in x.argv) for x in no_effort)
    assert cu.launch(p, tmp_path, "m", None, effort="high").argv == cu.launch(p, tmp_path, "m", None).argv


def test_custom_cli_effort_placeholder_becomes_each_harness_flag(tmp_path: Path) -> None:
    p = tmp_path / "p.md"
    p.write_text("x")
    cli = "wrapper {effort} {prompt}"
    assert wa.adapter_for("claude-code").launch(p, tmp_path, "m", cli, effort="low").argv[2] == f"wrapper --effort low {p}"
    assert wa.adapter_for("codex").launch(p, tmp_path, "m", cli, effort="low").argv[2] == \
        f"wrapper -c model_reasoning_effort=low {p}"
    assert wa.adapter_for("cursor").launch(p, tmp_path, "m", cli, effort="low").argv[2] == f"wrapper  {p}"
    assert wa.adapter_for("generic").launch(p, tmp_path, "m", cli, effort="low").argv[2] == f"wrapper  {p}"
    assert wa.adapter_for("claude-code").launch(p, tmp_path, "m", cli).argv[2] == f"wrapper  {p}"   # no level
    resumed = wa.adapter_for("claude-code").resume("sid", p, tmp_path, "m", "w {session_flag} {effort} {prompt}",
                                                   effort="max")
    assert resumed.argv[2] == f"w --resume sid --effort max {p}"
    for bad in ("w --effort={effort} {prompt}", "w <{effort} {prompt}"):
        assert wa.placeholder_problem(bad)
        with pytest.raises(wa.Unsupported):
            wa.adapter_for("claude-code").launch(p, tmp_path, "m", bad, effort="low")


def test_effort_note_only_when_a_level_is_set_and_the_command_names_no_effort() -> None:
    from specy_road.worker_adapter_parsers import effort_note  # noqa: PLC0415
    assert "takes no effort" in effort_note("w {prompt}", "high")
    assert effort_note("w {effort} {prompt}", "high") is None
    assert effort_note("w {prompt}", None) is None and effort_note(None, "high") is None


ENV_PROBE = "import os, sys\nopen(sys.argv[1], 'w').write(os.environ.get('CLAUDE_CODE_EFFORT_LEVEL', 'unset'))\n"


def test_the_worker_child_environment_has_no_claude_code_effort_level(tmp_path: Path, monkeypatch) -> None:
    repo = make_review_repo(tmp_path)
    script, out, prompt = tmp_path / "probe.py", tmp_path / "env.txt", tmp_path / "p.md"
    script.write_text(ENV_PROBE)
    prompt.write_text("x")
    monkeypatch.setenv("CLAUDE_CODE_EFFORT_LEVEL", "max")
    rec = ws.create_record(repo, "M1.1", "generic", "x", repo)
    launch = wa.adapter_for("generic").launch(prompt, repo, "x", f"{sys.executable} {script} {out} {{prompt}}")
    wr.run(repo, rec.worker_id, launch)
    assert out.read_text() == "unset"


def _harness(repo: Path, cli: str | None = None) -> None:
    """Roster ``opus`` on ``claude-code`` (and its ``channels.cli``), landed on ``dev`` like the profile."""
    roster = repo / "roadmap" / "orchestration.yaml"
    extra = "    harness: claude-code\n" + (f"    channels: {{cli: '{cli}'}}\n" if cli else "")
    roster.write_text(roster.read_text().replace("    family: anthropic\n", "    family: anthropic\n" + extra, 1))
    commit_profile(repo)


def test_prompt_cli_channel_substitutes_the_roles_effort_or_notes_its_absence(tmp_path: Path, capfd) -> None:
    repo = make_profile_repo(tmp_path)
    _harness(repo)
    prof_path = repo / "model-profiles" / "anthropic-claude" / "claude-opus-5-5.md"
    prof_path.write_text(prof_path.read_text().replace(shipped_anthropic_opus_cli_yaml_line(), "  cli: echo {effort} {prompt}"))
    commit_profile(repo)
    assert run_main(role_prompt, "M1.1", "--model", "opus", "--role", "coordinator", "--channel", "cli",
                "--repo-root", str(repo)) == 0
    out, err = capfd.readouterr()
    assert out.splitlines()[-1].startswith("--effort low ") and "takes no effort" not in err
    prof_path.write_text(prof_path.read_text().replace("  cli: echo {effort} {prompt}", "  cli: echo {prompt}"))
    commit_profile(repo)
    assert run_main(role_prompt, "M1.1", "--model", "opus", "--role", "coordinator", "--channel", "cli",
                "--repo-root", str(repo)) == 0
    out, err = capfd.readouterr()
    assert "--effort" not in out.splitlines()[-1] and err.count("takes no effort") == 1 and "effort low" in err


def test_delegate_passes_the_executor_effort_to_default_and_custom_commands(tmp_path: Path, capsys,
                                                                            monkeypatch) -> None:
    launches = []
    monkeypatch.setattr(ops, "spawn", lambda root, rec, launch, **kw: launches.append(launch))
    for name, cli in (("default", None), ("effort", "wrapper {effort} {prompt}"), ("none", "wrapper {prompt}")):
        (tmp_path / name).mkdir()
        repo = make_profile_repo(tmp_path / name)
        _harness(repo, cli)
        ops.delegate(repo, "M1.1", "opus")
        notes = capsys.readouterr().err.count("takes no effort")
        if cli is None:
            i = launches[-1].argv.index("--effort")
            assert launches[-1].argv[i + 1] == "medium" and notes == 0
        elif "{effort}" in cli:
            assert launches[-1].argv[2].startswith("wrapper --effort medium ") and notes == 0
        else:
            assert "--effort" not in launches[-1].argv[2] and notes == 1
