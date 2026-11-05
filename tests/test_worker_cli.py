"""``specy-road worker``: delegate, sync, leases, handoff/reclaim, hook, reconcile (slice 7c)."""

from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path

import pytest
import yaml

from tests.review_repo_helpers import git

from specy_road import worker_ops as ops
from specy_road import worker_state as ws
from specy_road.bundled_scripts import review_cli, worker_cli, worker_cli_render as wcr

from tests.worker_cli_helpers import run_worker_cli, wait_for_worker
from tests.worker_repo_helpers import FAKE, make_worker_repo, run_fake_harness_turn, worker_roster  # noqa: F401


def test_delegate_returns_at_once_and_is_idempotent(tmp_path: Path, capsys) -> None:
    repo, _ = make_worker_repo(tmp_path)
    assert run_worker_cli("worker", "delegate", "M1.1", "--model", "opus", "--json", "--repo-root", str(repo)) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["created"] and out["worker_id"] == "w-0001" and out["harness"] == "claude-code"
    assert out["worktree"] == str(repo.resolve())           # the claim's branch is checked out here
    assert (repo / "work" / "prompt-M1.1-executor-opus.md").is_file()
    assert run_worker_cli("worker", "delegate", "M1.1", "--model", "opus", "--json", "--repo-root", str(repo)) == 0
    assert json.loads(capsys.readouterr().out)["created"] is False
    rec = wait_for_worker(repo, "w-0001")
    assert rec.state == "idle" and rec.provider_session_id and rec.contract_hash and rec.billing_route == "claude_subscription"
    assert [e.type for e in ws.events_since(repo, "w-0001")][-1] == "completion"


def test_delegate_refusals(tmp_path: Path, capsys) -> None:
    repo, _ = make_worker_repo(tmp_path, max_workers=1)
    assert run_worker_cli("worker", "delegate", "M1.1", "--model", "sol", "--repo-root", str(repo)) == 1
    assert "executor role" in capsys.readouterr().err
    assert run_worker_cli("worker", "delegate", "M1.1", "--model", "nobody", "--repo-root", str(repo)) == 1
    assert "not in the roster" in capsys.readouterr().err
    assert run_worker_cli("worker", "delegate", "M9.9", "--model", "opus", "--repo-root", str(repo)) == 1
    assert "after pickup" in capsys.readouterr().err
    # Fill the one slot with an idle record (it owns its slot until `terminate`; a
    # `running` one with no live wrapper would be swept as dead), then try another leaf.
    rec = ws.create_record(repo, "M1.1", "generic", "x", repo)
    ws.set_state(repo, rec, "idle")
    import copy
    import json as _j
    nodes = _j.loads((repo / "roadmap" / "phases" / "M1.json").read_text())
    n2 = copy.deepcopy(nodes["nodes"][0]); n2.update(id="M1.2", codename="other", node_key="22222222-2222-5222-8222-222222222222",
                                                      planning_dir="planning/M1.2_other.md")
    nodes["nodes"].append(n2)
    (repo / "roadmap" / "phases" / "M1.json").write_text(_j.dumps(nodes))
    assert run_worker_cli("worker", "delegate", "M1.2", "--model", "opus", "--repo-root", str(repo)) == 1
    assert "max_workers" in capsys.readouterr().err


def test_op_id_makes_a_retry_answer_from_the_first_result(tmp_path: Path, capsys) -> None:
    repo, _ = make_worker_repo(tmp_path)
    assert run_worker_cli("worker", "delegate", "M1.1", "--model", "opus", "--op-id", "op-1", "--json", "--repo-root", str(repo)) == 0
    first = json.loads(capsys.readouterr().out)
    wait_for_worker(repo, first["worker_id"])
    assert run_worker_cli("worker", "delegate", "M1.1", "--model", "opus", "--op-id", "op-1", "--json", "--repo-root", str(repo)) == 0
    assert json.loads(capsys.readouterr().out) == first


def test_sync_delta_and_ack(tmp_path: Path, capsys) -> None:
    repo, _ = make_worker_repo(tmp_path)
    assert run_worker_cli("worker", "sync", "--repo-root", str(repo)) == 0
    assert "No new worker events" in capsys.readouterr().out
    run_worker_cli("worker", "delegate", "M1.1", "--model", "opus", "--repo-root", str(repo))
    wait_for_worker(repo, "w-0001")
    capsys.readouterr()
    assert run_worker_cli("worker", "sync", "--json", "--repo-root", str(repo)) == 0
    d = json.loads(capsys.readouterr().out)
    assert d["workers"][0]["events"][0]["seq"] == 1 and d["workers"][0]["events"][-1]["type"] == "completion"
    assert run_worker_cli("worker", "sync", "--ack", "--repo-root", str(repo)) == 0
    assert "completion" in capsys.readouterr().out
    assert run_worker_cli("worker", "sync", "--repo-root", str(repo)) == 0
    assert "No new worker events" in capsys.readouterr().out


def test_sync_wait_ends_on_an_event_or_times_out_with_exit_2(tmp_path: Path, capsys) -> None:
    repo, _ = make_worker_repo(tmp_path)
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    ws.set_state(repo, rec, "idle", pid=None)   # no wrapper to sweep: only the thread below writes events
    assert run_worker_cli("worker", "sync", "--wait", "--ack", "--repo-root", str(repo)) == 0   # `started` is unacked: no wait
    assert run_worker_cli("worker", "sync", "--wait", "--timeout", "0.3", "--repo-root", str(repo)) == 2
    assert capsys.readouterr().out.endswith("No new worker events.\n")   # the empty delta
    t0 = time.monotonic(); threading.Timer(0.5, lambda: ws.append_event(repo, rec, "output", source="worker", summary="mid-wait")).start()
    assert run_worker_cli("worker", "sync", "--wait", "--timeout", "10", "--json", "--repo-root", str(repo)) == 0 and time.monotonic() - t0 < 3
    assert [e["summary"] for e in json.loads(capsys.readouterr().out)["workers"][0]["events"]] == ["mid-wait"]


def test_message_resume_lease_and_interrupt(tmp_path: Path, capsys) -> None:
    repo, _ = make_worker_repo(tmp_path)
    run_worker_cli("worker", "delegate", "M1.1", "--model", "opus", "--repo-root", str(repo))
    rec = wait_for_worker(repo, "w-0001")
    assert run_worker_cli("worker", "interrupt", "w-0001", "--repo-root", str(repo)) == 2
    assert "unsupported by claude-code" in capsys.readouterr().err
    assert run_worker_cli("worker", "message", "w-0001", "--text", "also update docs", "--repo-root", str(repo)) == 0
    rec = wait_for_worker(repo, "w-0001")
    types = [e.type for e in ws.events_since(repo, "w-0001")]
    assert "message" in types and types.count("resumed") == 1 and types[-1] == "completion"
    ws.set_lease(repo, rec, "human")
    assert run_worker_cli("worker", "message", "w-0001", "--text", "x", "--repo-root", str(repo)) == 1
    assert "WORKER_LEASED_BY_HUMAN" in capsys.readouterr().err
    ws.set_lease(repo, rec, "broker")
    assert run_worker_cli("worker", "resume", "w-0001", "--repo-root", str(repo)) == 0
    wait_for_worker(repo, "w-0001")
    assert ws.load_record(repo, "w-0001").state == "idle"


def test_handoff_reclaim_round_trip_and_hook_evidence(tmp_path: Path, capsys) -> None:
    repo, _ = make_worker_repo(tmp_path)
    run_worker_cli("worker", "delegate", "M1.1", "--model", "opus", "--repo-root", str(repo))
    rec = wait_for_worker(repo, "w-0001")
    sid = rec.provider_session_id
    assert run_worker_cli("worker", "handoff", "w-0001", "--repo-root", str(repo)) == 0
    out = capsys.readouterr().out
    assert f"claude --resume {sid}" in out and "worker reclaim w-0001" in out
    rec = ws.load_record(repo, "w-0001")
    assert rec.lease["holder"] == "human" and rec.state == "handed_off" and rec.checkpoint["git_head"]
    # No hook evidence: reclaim flags the worker and bumps the epoch once.
    (repo / "src" / "b.py").write_text("x\n")
    assert run_worker_cli("worker", "reclaim", "w-0001", "--note", "told it to use sqlite", "--repo-root", str(repo)) == 0
    rec = ws.load_record(repo, "w-0001")
    assert rec.instruction_epoch == 1 and ws.FLAG_EXTERNAL in rec.flags and rec.lease["holder"] == "broker"
    ev = [e for e in ws.events_since(repo, "w-0001") if e.type == "intervention"][0]
    assert ev.authority == "human_authoritative" and "sqlite" in ev.summary and "b.py" in ev.detail["diff_stat"]
    # Second round: the hook saw the prompt, so no flag this time.
    ws.clear_flag(repo, rec, ws.FLAG_EXTERNAL)
    assert run_worker_cli("worker", "handoff", "w-0001", "--repo-root", str(repo)) == 0
    payload = json.dumps({"session_id": sid, "prompt": "do not add an abstraction"})
    import io
    sys.stdin = io.StringIO(payload)
    try:
        assert run_worker_cli("worker", "hook", "--format", "claude-code", "--repo-root", str(repo)) == 0
        sys.stdin = io.StringIO(json.dumps({"session_id": "someone-else", "prompt": "ignored"}))
        assert run_worker_cli("worker", "hook", "--format", "claude-code", "--repo-root", str(repo)) == 0
        sys.stdin = io.StringIO("not json")
        assert run_worker_cli("worker", "hook", "--format", "cursor", "--repo-root", str(repo)) == 0
        assert json.loads(capsys.readouterr().out.strip().splitlines()[-1]) == {"continue": True}
    finally:
        sys.stdin = sys.__stdin__
    lines = ops.interventions_path(repo, "w-0001").read_text().splitlines()
    assert len(lines) == 1 and "abstraction" in lines[0]
    assert run_worker_cli("worker", "reclaim", "w-0001", "--json", "--repo-root", str(repo)) == 0
    d = json.loads(capsys.readouterr().out)
    assert d["instruction_epoch"] == 2 and ws.FLAG_EXTERNAL not in d["flags"] and d["delta"]["prompts"] == ["do not add an abstraction"]
    assert run_worker_cli("worker", "reclaim", "w-0001", "--repo-root", str(repo)) == 1   # not handed off now


def test_hook_print_config_names_the_harness(capsys) -> None:
    for fmt in ("claude-code", "codex", "cursor"):
        assert run_worker_cli("worker", "hook", "--format", fmt, "--print-config") == 0
        out = capsys.readouterr()
        assert f"worker hook --format {fmt}" in json.dumps(json.loads(out.out)) and out.err.startswith("# ")


def test_reconcile_flags_a_touch_zone_breach(tmp_path: Path, capsys) -> None:
    repo, _ = make_worker_repo(tmp_path)
    run_worker_cli("worker", "delegate", "M1.1", "--model", "opus", "--repo-root", str(repo))
    rec = wait_for_worker(repo, "w-0001")
    ws.take_checkpoint(repo, rec)
    capsys.readouterr()
    assert run_worker_cli("worker", "reconcile", "w-0001", "--json", "--repo-root", str(repo)) == 0
    assert json.loads(capsys.readouterr().out)["delta"]["needs_reconcile"] is False
    # The toolkit's own files are never a breach.
    (repo / "work").mkdir(exist_ok=True)
    (repo / "work" / "brief-M1.1.md").write_text("brief\n")
    (repo / "roadmap" / "registry.yaml").write_text((repo / "roadmap" / "registry.yaml").read_text() + "# note\n")
    assert run_worker_cli("worker", "reconcile", "w-0001", "--json", "--repo-root", str(repo)) == 0
    assert json.loads(capsys.readouterr().out)["delta"]["needs_reconcile"] is False
    (repo / "README.md").write_text("outside\n")
    (repo / "work" / "notes.md").write_text("under work/, but not the leaf's bookkeeping\n")
    git(repo, "add", "-f", "work/notes.md", "README.md")   # tracked: an untracked file is only a warning (M11.40)
    git(repo, "commit", "-qm", "worker notes")
    assert run_worker_cli("worker", "reconcile", "w-0001", "--repo-root", str(repo)) == 0
    out = capsys.readouterr().out
    assert "OUTSIDE touch zones: README.md" in out and "OUTSIDE touch zones: work/notes.md" in out
    assert "needs_reconcile=True" in out
    assert "brief-M1.1" not in out
    assert ws.FLAG_RECONCILE in ws.load_record(repo, "w-0001").flags


def test_terminate_a_live_worker(tmp_path: Path) -> None:
    repo, script = make_worker_repo(tmp_path)
    spec = tmp_path / "slow.json"
    spec.write_text(json.dumps({"lines": [{"type": "system", "subtype": "init", "session_id": "slow"}], "sleep": 30}))
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    from specy_road.worker_adapters import Launch
    from specy_road.worker_runner import pid_alive, spawn
    spawn(repo, rec, Launch([sys.executable, str(script), str(spec)]))
    for _ in range(50):
        if ws.load_record(repo, "w-0001").provider_session_id:
            break
        time.sleep(0.1)
    assert pid_alive(rec.pid)
    assert run_worker_cli("worker", "terminate", "w-0001", "--repo-root", str(repo)) == 0
    rec = ws.load_record(repo, "w-0001")
    assert rec.state == "terminated" and rec.pid is None
    time.sleep(0.5)
    assert ws.load_record(repo, "w-0001").state == "terminated"     # the wrapper's exit did not overwrite it


def test_adopt_open_list_status_and_handoff_status(tmp_path: Path, capsys) -> None:
    repo, _ = make_worker_repo(tmp_path)
    assert run_worker_cli("worker", "adopt", "--node", "M1.1", "--harness", "codex", "--session", "11111111-2222-4333-8444-555555555555", "--json", "--repo-root", str(repo)) == 0
    d = json.loads(capsys.readouterr().out)
    assert d["lease"]["holder"] == "native" and d["provider_session_id"] == "11111111-2222-4333-8444-555555555555"
    assert run_worker_cli("worker", "message", "w-0001", "--text", "x", "--repo-root", str(repo)) == 1
    assert "WORKER_NATIVE_OWNED" in capsys.readouterr().err
    assert run_worker_cli("worker", "open", "w-0001", "--repo-root", str(repo)) == 0
    assert "codex resume 11111111-2222-4333-8444-555555555555" in capsys.readouterr().out
    assert run_worker_cli("worker", "list", "--repo-root", str(repo)) == 0
    assert "w-0001  M1.1" in capsys.readouterr().out
    assert run_worker_cli("worker", "status", "w-0001", "--json", "--repo-root", str(repo)) == 0
    assert json.loads(capsys.readouterr().out)["recent_events"][-1]["type"] == "adopted"
    assert run_worker_cli("worker", "events", "w-0001", "--since", "1", "--repo-root", str(repo)) == 0
    assert "#2" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        review_cli.main(["handoff", "status", "--repo-root", str(repo)])
    assert "Workers: w-0001 (M1.1 codex idle, lease native)" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        review_cli.main(["handoff", "status", "--json", "--repo-root", str(repo)])
    assert json.loads(capsys.readouterr().out)["workers"][0]["worker_id"] == "w-0001"


def test_launch_events_ack_time_and_timeline(tmp_path: Path, capsys) -> None:
    """A1: launched and first_output bracket the harness; A2: the ack is timed; A3: timeline per turn."""
    repo, _ = make_worker_repo(tmp_path)
    run_worker_cli("worker", "delegate", "M1.1", "--model", "opus", "--repo-root", str(repo))
    wait_for_worker(repo, "w-0001")
    evs = ws.events_since(repo, "w-0001")
    types = [e.type for e in evs]
    assert types[:3] == ["started", "launched", "first_output"] and types[-1] == "completion"
    launched = evs[1]
    assert launched.source == "system" and launched.authority == "system"
    assert launched.detail == {"argv0": "sh", "harness": "claude-code", "resumed": False, "model": None}   # custom cli
    assert evs[2].detail is None
    capsys.readouterr()
    # A3 by node id, before any ack: the last phase is unknown.
    assert run_worker_cli("worker", "timeline", "M1.1", "--repo-root", str(repo)) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith("w-0001 M1.1 timeline") and len(out) == 5
    assert out[1].startswith("  delegated -> launched: ") and out[1].endswith("s")
    assert out[4] == "  end -> acked: unknown"
    # A2: the ack records when, and the seq, without changing what sync returns.
    assert run_worker_cli("worker", "sync", "--ack", "--json", "--repo-root", str(repo)) == 0
    d = json.loads(capsys.readouterr().out)
    assert d["acked"] is True and d["workers"][0]["events"][-1]["seq"] == len(evs)
    marks = yaml.safe_load((ws.workers_dir(repo) / "sync.yaml").read_text())
    assert marks["w-0001"]["seq"] == len(evs) and marks["w-0001"]["acked_at"] >= evs[-1].at   # ISO strings order
    assert run_worker_cli("worker", "timeline", "w-0001", "--json", "--repo-root", str(repo)) == 0
    t = json.loads(capsys.readouterr().out)
    assert t["worker_id"] == "w-0001" and t["node_id"] == "M1.1"
    assert all(isinstance(t["phases"][k], float) for k in ("delegated_to_launched", "launched_to_first_output",
                                                          "first_output_to_end", "end_to_acked"))
    # A resumed turn: launched says so, and the earlier ack does not count for the new turn's end.
    assert run_worker_cli("worker", "message", "w-0001", "--text", "again", "--repo-root", str(repo)) == 0
    wait_for_worker(repo, "w-0001")
    capsys.readouterr()
    second = [e for e in ws.events_since(repo, "w-0001") if e.type == "launched"]
    assert len(second) == 2 and second[1].detail["resumed"] is True
    assert run_worker_cli("worker", "timeline", "w-0001", "--json", "--repo-root", str(repo)) == 0
    t = json.loads(capsys.readouterr().out)
    assert t["phases"]["end_to_acked"] is None and isinstance(t["phases"]["first_output_to_end"], float)
    assert run_worker_cli("worker", "timeline", "M9.9", "--repo-root", str(repo)) == 1
    assert "no worker for M9.9" in capsys.readouterr().err


def test_timeline_arithmetic_and_unknown_phases() -> None:
    """The phase sums from a fixed log; a missing boundary reads unknown, an ack short of the end does not count."""
    class Rec:
        worker_id, node_id = "w-0007", "M2.1"
    def ev(seq, at, type_, source="system", detail=None):
        return {"seq": seq, "at": f"2026-10-30T10:00:{at:02d}+00:00", "type": type_, "source": source, "detail": detail}
    log = [ev(1, 0, "started", "broker"), ev(2, 3, "launched"), ev(3, 5, "first_output"),
           ev(4, 5, "started", "worker"), ev(5, 20, "turn_completed", "worker"),
           ev(6, 21, "completion", "worker", {"exit": 0, "ready": True})]
    t = wcr.timeline(Rec(), log, {"seq": 6, "acked_at": "2026-10-30T10:01:01+00:00"})
    assert t["phases"] == {"delegated_to_launched": 3.0, "launched_to_first_output": 2.0,
                           "first_output_to_end": 15.0, "end_to_acked": 41.0}
    assert wcr.timeline_lines(t)[1:] == ["  delegated -> launched: 3s", "  launched -> first_output: 2s",
                                         "  first_output -> end: 15s", "  end -> acked: 41s"]
    # The ack reached seq 4 only: the turn's end was not acknowledged yet.
    assert wcr.timeline(Rec(), log, {"seq": 4, "acked_at": "2026-10-30T10:00:30+00:00"})["phases"]["end_to_acked"] is None
    # An error with an exit code ends the turn too; no first_output leaves its two phases unknown.
    log2 = [ev(1, 0, "started", "broker"), ev(2, 2, "launched"), ev(3, 9, "error", "worker", {"exit": 1})]
    assert wcr.timeline(Rec(), log2, None)["phases"] == {"delegated_to_launched": 2.0, "launched_to_first_output": None,
                                                        "first_output_to_end": None, "end_to_acked": None}
    # An adopted worker never launched anything: every phase unknown, and the lines say so.
    t = wcr.timeline(Rec(), [ev(1, 0, "started", "broker"), ev(2, 1, "adopted", "orchestrator")], None)
    assert set(t["phases"].values()) == {None} and all(line.endswith("unknown") for line in wcr.timeline_lines(t)[1:])


def test_usage_events_per_turn_and_the_usage_command(tmp_path: Path, capsys) -> None:
    """M10.2 A2/A3: one usage event per turn end, Claude's running cost as a delta; `worker usage` per attempt and node."""
    repo, script = make_worker_repo(tmp_path)
    rec = json.loads((Path(__file__).parent / "fixtures/worker_usage/turn_end_lines.json").read_text())   # real, sanitized
    init, first, resumed = rec["claude-code"]["lines"]   # one session: the resumed turn reports the session's whole total
    claude = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    run_fake_harness_turn(repo, script, claude, [init, first])
    run_fake_harness_turn(repo, script, claude, [init, resumed])
    codex = ws.create_record(repo, "M1.1", "codex", "sol", repo)
    run_fake_harness_turn(repo, script, codex, rec["codex"]["lines"])
    run_fake_harness_turn(repo, script, codex, [{"type": "turn.failed", "error": {"message": "quota"}}], exit_code=1)   # constructed
    cu = [e.detail for e in ws.events_since(repo, claude.worker_id) if e.type == "usage"]
    assert [u["cost_usd"] for u in cu] == [1.0474079, 0.162736] and [u["session_cost_usd"] for u in cu] == [1.0474079, 1.2101441]
    assert cu[1] == {"input_tokens": 380001, "cached_input_tokens": 376181, "output_tokens": 2849, "reasoning_tokens": 123,
                     "cost_usd": 0.162736, "cost_is_estimate": True, "num_turns": 4, "harness_version": "2.1.312",
                     "session_cost_usd": 1.2101441, "requested_model": None, "observed_model": "claude-opus-5-5"}
    xu = [e for e in ws.events_since(repo, codex.worker_id) if e.type == "usage"]
    assert xu[0].detail["reasoning_tokens"] == 0 and xu[0].detail["cost_usd"] is None
    assert set(xu[1].detail.values()) == {None} and xu[1].authority == "worker_suggestion"   # nothing reported: nulls
    capsys.readouterr()
    assert run_worker_cli("worker", "usage", "M1.1", "--json", "--repo-root", str(repo)) == 0
    d = json.loads(capsys.readouterr().out)
    assert [(a["attempt"], a["harness"], a["model"], a["turns"], a["cost_usd"]) for a in d["attempts"]] == [
        (1, "claude-code", "opus", 2, 1.210144), (2, "codex", "sol", 2, None)]
    assert d["total"] == {"turns": 4, "input_tokens": 1686117, "cached_input_tokens": 1612673, "output_tokens": 16112,
                          "reasoning_tokens": 4826, "cost_usd": 1.210144, "num_turns": 23, "cost_is_estimate": True}
    assert run_worker_cli("worker", "usage", "M1.1", "--repo-root", str(repo)) == 0
    assert capsys.readouterr().out.splitlines() == [
        "M1.1 usage (2 attempt(s); ? = not reported)",
        "  attempt 1 w-0001 claude-code 2.1.312/opus, 2 turn(s): in 1671333 (1600385 cached), out 16107, reasoning 4826, $1.2101 est.",
        "  attempt 2 w-0002 codex/sol, 2 turn(s): in 14784 (12288 cached), out 5, reasoning 0, $?",
        "  total, 4 turn(s): in 1686117 (1612673 cached), out 16112, reasoning 4826, $1.2101 est."]
    assert run_worker_cli("worker", "usage", "w-0002", "--json", "--repo-root", str(repo)) == 0
    assert json.loads(capsys.readouterr().out)["total"]["cost_usd"] is None
    assert run_worker_cli("worker", "usage", "M9.9", "--repo-root", str(repo)) == 1


def test_usage_event_schema_needs_every_field_nullable_never_missing() -> None:
    """M10.2 A1: a usage event carries all eight fields; null is allowed, a missing field or a wrong type is not."""
    from specy_road.worker_adapter_parsers import USAGE_FIELDS
    ev = {"seq": 1, "worker_id": "w-0001", "at": "2026-11-01T00:00:00+00:00", "type": "usage", "source": "worker",
          "authority": "worker_suggestion", "summary": "usage", "epoch": 0}
    nulls = dict.fromkeys(USAGE_FIELDS)
    assert ws.schema_errors({**ev, "detail": nulls}, "worker-event.schema.json") == []
    assert ws.schema_errors({**ev, "detail": {**nulls, "input_tokens": 0, "cost_usd": 0.0}}, "worker-event.schema.json") == []
    for bad in ({}, {**nulls, "output_tokens": "9"}, {k: v for k, v in nulls.items() if k != "num_turns"}):
        assert ws.schema_errors({**ev, "detail": bad}, "worker-event.schema.json")
    assert ws.schema_errors(ev, "worker-event.schema.json")   # no detail at all
