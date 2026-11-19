"""``specy-road worker``: delegate, sync, leases, handoff/reclaim, hook, reconcile (slice 7c)."""

from __future__ import annotations

from tests.support import REPO
import json
import sys
import threading
import time
from pathlib import Path

import pytest
import yaml

from tests.support.same.git_84c8ad8f55f9 import git

from specy_road.orchestration.workers import worker_ops as ops
from specy_road.orchestration.workers import worker_state as ws
from specy_road.bundled_scripts import review_cli, worker_cli
from specy_road.orchestration.workers import worker_cli_render as wcr

from tests.support.cli import run_worker_cli
from tests.support.harness import make_worker_repo, run_fake_harness_turn, wait_for_worker
from tests.support.review import make_review_repo, git as git_folded
from specy_road.review_files import reviews_root
import os
from tests.support.review import git as git_folded
from specy_road.orchestration.workers import worker_lease as ww
from tests.support.extracted.folded_review_ops import idle_record
from tests.support.harness import FAKE, worker_roster
from tests.support.extracted.worker_repos import worker_repo
from specy_road.orchestration.workers import worker_adapters as wa
from specy_road.orchestration.workers import worker_runner as wr
from specy_road.bundled_scripts.role_prompt import build_prompt
from specy_road.orchestration.workers.worker_cli_render import sync_event_lines
from specy_road.orchestration.workers.worker_process import group_members
from tests.support.bounded_wait import pause, wait_until


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


@pytest.mark.slow
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


@pytest.mark.slow
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


@pytest.mark.slow
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


@pytest.mark.slow
def test_terminate_a_live_worker(tmp_path: Path) -> None:
    repo, script = make_worker_repo(tmp_path)
    spec = tmp_path / "slow.json"
    spec.write_text(json.dumps({"lines": [{"type": "system", "subtype": "init", "session_id": "slow"}], "sleep": 30}))
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    from specy_road.orchestration.workers.worker_adapters import Launch
    from specy_road.orchestration.workers.worker_runner import pid_alive, spawn
    spawn(repo, rec, Launch([sys.executable, str(script), str(spec)]))
    for _ in range(50):
        if ws.load_record(repo, "w-0001").provider_session_id:
            break
        pause(0.1)
    assert pid_alive(rec.pid)
    wrapper_pid = rec.pid
    assert run_worker_cli("worker", "terminate", "w-0001", "--repo-root", str(repo)) == 0
    rec = ws.load_record(repo, "w-0001")
    assert rec.state == "terminated" and rec.pid is None
    wait_until(lambda: not pid_alive(wrapper_pid), timeout=5, message="wrapper did not exit")
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


@pytest.mark.slow
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
    rec = json.loads((REPO / "tests" / "fixtures/worker_usage/turn_end_lines.json").read_text())   # real, sanitized
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
    from specy_road.orchestration.workers.worker_adapter_parsers import USAGE_FIELDS
    ev = {"seq": 1, "worker_id": "w-0001", "at": "2026-11-01T00:00:00+00:00", "type": "usage", "source": "worker",
          "authority": "worker_suggestion", "summary": "usage", "epoch": 0}
    nulls = dict.fromkeys(USAGE_FIELDS)
    assert ws.schema_errors({**ev, "detail": nulls}, "worker-event.schema.json") == []
    assert ws.schema_errors({**ev, "detail": {**nulls, "input_tokens": 0, "cost_usd": 0.0}}, "worker-event.schema.json") == []
    for bad in ({}, {**nulls, "output_tokens": "9"}, {k: v for k, v in nulls.items() if k != "num_turns"}):
        assert ws.schema_errors({**ev, "detail": bad}, "worker-event.schema.json")
    assert ws.schema_errors(ev, "worker-event.schema.json")   # no detail at all



# --- B8 -----------------------------------------------------------------------

# One test per finding: a completed worker still owns its leaf; lifecycle transitions are one
# transaction each; the guard refuses shell shapes it cannot follow and `git -C` into another
# tree, and denies a bare commit; an embedded placeholder is refused; the default session id is
# stable across processes and `touch` keeps the paths; a skipped skill is never adopted or
# overwritten; a stale worktree directory is refused; the GUI reports the v2 session and requires
# a reject reason; op ids bind their arguments; signing without a roster key is refused early; a
# foreign skill link is left alone; a dead wrapper frees the leaf; terminate refuses an
# unverifiable pid and does not signal an adopted session; READY binds to the branch; a profile
# path cannot escape the repo; `--harness` cannot override the roster; a plan with no coordinator
# says so; search results are delimited; the verifier's byte cap is a cap.

def test_a_stale_worktree_directory_is_refused(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    git_folded(repo, "checkout", "-q", "dev")
    stale = reviews_root(repo).parent / ".worktrees" / "thing"
    stale.mkdir(parents=True)
    with pytest.raises(ws.WorkerError, match="not a git worktree"):
        ops.worktree_for(repo, "feature/rm-thing", "thing", None)
    with pytest.raises(ws.WorkerError, match="checked out, not the claim's branch"):
        ops.worktree_for(repo, "feature/rm-thing", "thing", repo)



# Session ids are validated and resume commands rendered with shlex.
# A placeholder is a whole shell word; embedded or multi-word quoted forms are refused, and
# validation and substitution walk the same tokens.
# `message --op-id` binds the message text, and a retry whose file is gone answers from the
# outbox.
# The hook matches by harness and id, refuses ambiguity, and never waits long for the workers
# lock; `delegate` keeps its preflight outside the lock.
# Dead wrappers on any leaf are reaped by `sync` and before the `max_workers` count; `delegate`
# refuses a dirty checkout; a crashed reclaim is repaired, not repeated; `sync --ack` is
# serialised.
# `message` from a linked worktree, and the brief in the same checkout.

def test_handoff_prints_a_quoted_command(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path)
    rec = idle_record(repo, sid="a.b:c-d")
    assert run_worker_cli("worker", "handoff", rec.worker_id, "--repo-root", str(repo)) == 0
    assert "claude --resume a.b:c-d" in capsys.readouterr().out
    assert run_worker_cli("worker", "open", rec.worker_id, "--repo-root", str(repo)) == 0
    assert "resume:   claude --resume a.b:c-d" in capsys.readouterr().out



def test_delegate_runs_preflight_outside_the_workers_lock(tmp_path: Path, monkeypatch) -> None:
    repo, _ = make_worker_repo(tmp_path)
    seen: dict[str, bool] = {}

    def probe(entry, root):
        with ww.try_workers_lock(root, 0.2) as held:   # re-entrant when this thread holds it
            seen["free"] = held
        # A stranger (another thread) must be able to take the lock while preflight runs.
        got = []
        t = threading.Thread(target=lambda: [got.append(h) for h in [ww.try_workers_lock(root, 0.5).__enter__()]])
        t.start()
        t.join(2)
        seen["other_thread"] = bool(got and got[0])
    monkeypatch.setattr(ops, "preflight", probe)
    rec, created = ops.delegate(repo, "M1.1", "opus")
    assert created and seen == {"free": True, "other_thread": True}
    wait_for_worker(repo, rec.worker_id)



# --- F11 (b) ---------------------------------------------------------------------

@pytest.mark.slow
def test_delegate_refuses_a_checkout_with_uncommitted_changes(tmp_path: Path, capsys) -> None:
    # Pre-release review: the worker would edit the same tree, overwriting this
    # work, and `reconcile` could not tell its edits from it. Only the leaf's
    # untracked bookkeeping is exempt, not the rest of work/ (re-review N2).
    repo, _ = make_worker_repo(tmp_path)
    (repo / ".gitignore").write_text("work/.workers/\nwork/prompt-*.md\n")   # as the project template: briefs tracked
    (repo / "work").mkdir(exist_ok=True)
    (repo / "work" / "implementation-summary-M1.1.md").write_text("committed summary\n")
    git_folded(repo, "add", ".gitignore", "work/implementation-summary-M1.1.md")
    git_folded(repo, "commit", "-qm", "template ignores")
    (repo / "work" / "brief-M1.1.md").write_text("pickup's brief, untracked\n")
    (repo / "work" / "notes.md").write_text("the human's notes\n")
    (repo / "work" / "implementation-summary-M1.1.md").write_text("edited before delegate\n")
    (repo / "pre.txt").write_text("dirt before delegate\n")
    (repo / "src" / "a.py").write_text("edited before delegate\n")
    prompt = repo / "work" / "prompt-M1.1-executor-opus.md"   # third review F4: nothing is written before the check
    prompt.write_text("an earlier prompt\n")
    assert run_worker_cli("worker", "delegate", "M1.1", "--model", "opus", "--repo-root", str(repo)) == 1
    err = capsys.readouterr().err
    assert ("uncommitted changes" in err and "commit or stash" in err
            and "pre.txt, src/a.py, work/implementation-summary-M1.1.md, work/notes.md;" in err)
    assert (repo / "src" / "a.py").read_text() == "edited before delegate\n" and not ws.list_records(repo)
    (repo / "pre.txt").unlink()
    (repo / "work" / "notes.md").unlink()
    git_folded(repo, "checkout", "--", "src/a.py", "work/implementation-summary-M1.1.md")
    index = repo / ".git" / "index"
    saved = index.read_bytes()
    index.write_bytes(b"not an index")   # re-review N9: a status git cannot read is not a clean tree
    assert run_worker_cli("worker", "delegate", "M1.1", "--model", "opus", "--repo-root", str(repo)) == 1
    assert "cannot read `git status`" in capsys.readouterr().err and not ws.list_records(repo)
    assert prompt.read_text() == "an earlier prompt\n"
    index.write_bytes(saved)
    assert run_worker_cli("worker", "delegate", "M1.1", "--model", "opus", "--repo-root", str(repo)) == 0   # only the brief left
    wait_for_worker(repo, "w-0001")



def test_delegate_in_the_same_checkout_writes_the_missing_brief(tmp_path: Path) -> None:
    repo, _ = make_worker_repo(tmp_path)
    assert not (repo / "work" / "brief-M1.1.md").exists()
    rec, _c = ops.delegate(repo, "M1.1", "opus")
    assert rec.worktree == str(repo.resolve()) and (repo / "work" / "brief-M1.1.md").is_file()
    wait_for_worker(repo, rec.worker_id)
    assert os.path.getsize(repo / "work" / "brief-M1.1.md") > 0



@pytest.mark.slow
def test_worker_list_and_sync_show_worktree(tmp_path: Path, capsys) -> None:
    script = tmp_path / "fake.py"
    script.write_text(FAKE)
    repo = make_review_repo(
        tmp_path,
        orchestration=worker_roster(f"{sys.executable} {script} {{prompt}} {{session}}"),
    )
    run_worker_cli("worker", "delegate", "M1.1", "--model", "opus", "--repo-root", str(repo))
    rec = wait_for_worker(repo, "w-0001")
    capsys.readouterr()
    assert run_worker_cli("worker", "list", "--repo-root", str(repo)) == 0
    assert f"worktree={rec.worktree}" in capsys.readouterr().out
    capsys.readouterr()
    assert run_worker_cli("worker", "sync", "--repo-root", str(repo)) == 0
    assert f"worktree={rec.worktree}" in capsys.readouterr().out



# Worker hand-off, reconcile reporting, sync/list messages, and the merge finish notice.

def test_sync_and_list_surface_the_harness_final_message(tmp_path: Path, capsys) -> None:
    limit = "You've hit your 5-hour limit · resets 6:20pm"
    script = tmp_path / "limit.py"
    script.write_text(
        f'''import json, sys
print(json.dumps({{"type": "system", "subtype": "init", "session_id": "s1", "model": "fake"}}), flush=True)
print(json.dumps({{"type": "result", "subtype": "success", "is_error": True, "result": "{limit}",
  "session_id": "s1"}}), flush=True)
sys.exit(1)
'''
    )
    repo = make_review_repo(
        tmp_path,
        orchestration=worker_roster(f"{sys.executable} {script} {{prompt}} {{session}}"),
    )
    (repo / ".gitignore").write_text("work/\n")
    git_folded(repo, "add", ".gitignore")
    git_folded(repo, "commit", "-qm", "ignore work")
    run_worker_cli("worker", "delegate", "M1.1", "--model", "opus", "--repo-root", str(repo))
    rec = wait_for_worker(repo, "w-0001")
    assert rec.state == "failed"
    capsys.readouterr()
    assert run_worker_cli("worker", "sync", "--repo-root", str(repo)) == 0
    sync_out = capsys.readouterr().out
    assert limit in sync_out
    assert run_worker_cli("worker", "list", "--all", "--repo-root", str(repo)) == 0
    assert limit in capsys.readouterr().out



@pytest.mark.slow
@pytest.mark.parametrize("exit_type, exit_summary, exit_detail", [
    ("completion", "exit 0; READY file missing", {"exit": 0, "ready": False}),
    ("error", "exit 1; see w-0001.log", {"exit": 1, "ready": False}),
])
def test_sync_shows_an_acknowledged_final_message_with_the_later_exit(
    tmp_path: Path, capsys, exit_type: str, exit_summary: str, exit_detail: dict,
) -> None:
    final = "Stop: write READY in main checkout reviews dir"
    repo = worker_repo(tmp_path)
    run_worker_cli("worker", "delegate", "M1.1", "--model", "opus", "--repo-root", str(repo))
    rec = wait_for_worker(repo, "w-0001")
    ws.append_event(repo, rec, "output", source="worker", summary="(truncated)", detail={"message": final})
    assert run_worker_cli("worker", "sync", "--ack", "--repo-root", str(repo)) == 0   # acked while the turn runs
    ws.append_event(repo, rec, exit_type, source="worker", summary=exit_summary, detail=exit_detail)
    capsys.readouterr()
    assert run_worker_cli("worker", "sync", "--ack", "--repo-root", str(repo)) == 0
    assert final in capsys.readouterr().out
    # The next turn exits with no message of its own: the earlier turn's is not shown for it.
    ws.append_event(repo, rec, exit_type, source="worker", summary=exit_summary, detail=exit_detail)
    assert run_worker_cli("worker", "sync", "--repo-root", str(repo)) == 0
    assert final not in capsys.readouterr().out



# One test per finding: records survive a concurrent writer (the wrapper no longer writes a stale
# copy back), two delegates on one leaf launch once, terminate reaches the harness and its
# children, an op id names one operation, an older attempt's READY does not complete a new worker,
# and the harness does not inherit the wrapper's PYTHONPATH.

def test_concurrent_delegates_on_one_leaf_launch_once(tmp_path: Path) -> None:
    repo, _ = make_worker_repo(tmp_path, max_workers=4)
    results: list = []

    def go() -> None:
        try:
            results.append(ops.delegate(repo, "M1.1", "opus"))
        except Exception as e:  # noqa: BLE001
            results.append(e)

    threads = [threading.Thread(target=go) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    recs = [r for r in results if isinstance(r, tuple)]
    assert len(recs) == 4 and sum(1 for _r, created in recs if created) == 1
    assert {r.worker_id for r, _c in recs} == {"w-0001"}
    wait_for_worker(repo, "w-0001")



@pytest.mark.slow
def test_terminate_reaches_the_harness_and_its_children(tmp_path: Path) -> None:
    repo, _ = make_worker_repo(tmp_path)
    marker = tmp_path / "ticks"
    child = tmp_path / "child.py"
    child.write_text(f"import time\nwhile True:\n    open({str(marker)!r}, 'a').write('x')\n    time.sleep(0.1)\n")
    harness = tmp_path / "harness.py"
    harness.write_text("import json, subprocess, sys, time\n"
                       f"subprocess.Popen([sys.executable, {str(child)!r}])\n"
                       "print(json.dumps({'type': 'system', 'subtype': 'init', 'session_id': 'h'}), flush=True)\n"
                       "time.sleep(30)\n")
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    wr.spawn(repo, rec, wa.Launch([sys.executable, str(harness)]))
    for _ in range(50):
        if marker.is_file() and ws.load_record(repo, rec.worker_id).provider_session_id:
            break
        pause(0.1)
    assert marker.is_file()
    pgid = ws.load_record(repo, rec.worker_id).pgid
    ops.terminate(repo, rec.worker_id)
    wait_until(lambda: not group_members(pgid), timeout=5, message="the harness group did not exit")
    assert ws.load_record(repo, rec.worker_id).state == "terminated"



# One test per finding: a prompt containing `<prompt>` cannot break out of the shell quoting; the
# session id chosen up front survives the spawn; a completed worker can take a review `block` as a
# message and a turn's READY is judged against that turn; a linked worktree gets the brief; the
# guard scopes tree-only commands to this worktree and sees `checkout -f`, `restore <path>`, brace
# groups, `eval` and `$(…)`; an op id is bound to its target; handoff refuses a closed worker;
# hook prompts are attributed by line, not by second; adopt refuses a duplicate; reconcile treats
# an unbuildable prompt as a contract change; Codex resume keeps its sandbox; reviews_root stays
# inside a nested project; the CGNAT range is off-host.

def test_delegate_into_a_linked_worktree_carries_the_brief(tmp_path: Path) -> None:
    repo, _ = make_worker_repo(tmp_path)
    (repo / "work").mkdir(exist_ok=True)
    (repo / "work" / "brief-M1.1.md").write_text("# Brief\n")
    git_folded(repo, "checkout", "-q", "dev")
    rec, created = ops.delegate(repo, "M1.1", "opus")
    assert created and Path(rec.worktree) != repo.resolve()
    assert (Path(rec.worktree) / "work" / "brief-M1.1.md").read_text() == "# Brief\n"
    wait_for_worker(repo, rec.worker_id)
    text, _p, err = build_prompt(repo, "M1.1", role="executor", model="opus")
    assert err is None and str(reviews_root(repo) / "M1.1") in text



def test_an_op_id_is_bound_to_its_target(tmp_path: Path) -> None:
    repo, _ = make_worker_repo(tmp_path, max_workers=4)
    assert run_worker_cli("worker", "delegate", "M1.1", "--model", "opus", "--op-id", "op-1", "--repo-root", str(repo)) == 0
    wait_for_worker(repo, "w-0001")
    assert run_worker_cli("worker", "delegate", "M9.9", "--model", "opus", "--op-id", "op-1", "--repo-root", str(repo)) != 0
    assert [r.worker_id for r in ws.list_records(repo)] == ["w-0001"]   # no replayed result, no second worker


_UNTIL_VALUES = ("completion", "error", "intervention", "completion,error", "error,intervention")



def _idle_rec(repo: Path) -> ws.WorkerRecord:
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    ws.set_state(repo, rec, "idle", pid=None)
    return rec



def _ack_all(repo: Path) -> None:
    run_worker_cli("worker", "sync", "--wait", "--ack", "--repo-root", str(repo))



# Worker sync --until, collapsed tool-use output, rework after completed, and ready-only resume.

@pytest.mark.parametrize("until", _UNTIL_VALUES)
def test_sync_wait_until_exits_0_when_the_condition_is_met(tmp_path: Path, capsys, until: str) -> None:
    repo, _ = make_worker_repo(tmp_path)
    rec = _idle_rec(repo)
    _ack_all(repo)
    capsys.readouterr()
    want = {t.strip() for t in until.split(",")}
    if "completion" in want:
        ws.append_event(repo, rec, "completion", source="worker", summary="exit 0; READY file present",
                        detail={"exit": 0, "ready": True})
    elif "error" in want:
        ws.append_event(repo, rec, "error", source="worker", summary="exit 1", detail={"exit": 1})
    else:
        ws.append_event(repo, rec, "intervention", source="human", authority="human_authoritative", summary="stop")
    assert run_worker_cli("worker", "sync", "--wait", "--until", until, "--timeout", "5",
                          "--json", "--repo-root", str(repo)) == 0
    evs = json.loads(capsys.readouterr().out)["workers"][0]["events"]
    assert evs[-1]["type"] in want



@pytest.mark.parametrize("until", ("completion", "error", "intervention"))
def test_sync_wait_until_exits_2_on_timeout_with_no_events(tmp_path: Path, capsys, until: str) -> None:
    repo, _ = make_worker_repo(tmp_path)
    _idle_rec(repo)
    _ack_all(repo)
    capsys.readouterr()
    assert run_worker_cli("worker", "sync", "--wait", "--until", until, "--timeout", "0.3",
                          "--repo-root", str(repo)) == 2
    assert "No new worker events." in capsys.readouterr().out



@pytest.mark.parametrize("until", ("completion", "error", "intervention"))
def test_sync_wait_until_exits_2_on_timeout_with_unmatched_events(tmp_path: Path, capsys, until: str) -> None:
    repo, _ = make_worker_repo(tmp_path)
    rec = _idle_rec(repo)
    _ack_all(repo)
    capsys.readouterr()
    ws.append_event(repo, rec, "output", source="worker", summary="(tool use)")
    assert run_worker_cli("worker", "sync", "--wait", "--until", until, "--timeout", "0.3",
                          "--repo-root", str(repo)) == 2
    out = capsys.readouterr().out
    assert "(tool use)" in out or "tool uses" in out



def test_sync_wait_until_completion_waits_past_output_before_completion(tmp_path: Path, capsys) -> None:
    repo, _ = make_worker_repo(tmp_path)
    rec = _idle_rec(repo)
    _ack_all(repo)
    capsys.readouterr()
    for _ in range(3):
        ws.append_event(repo, rec, "output", source="worker", summary="(tool use)")
    threading.Timer(0.4, lambda: ws.append_event(repo, rec, "completion", source="worker",
                                                   summary="exit 0; READY file present",
                                                   detail={"exit": 0, "ready": True})).start()
    t0 = time.monotonic()
    assert run_worker_cli("worker", "sync", "--wait", "--until", "completion", "--timeout", "10",
                          "--json", "--repo-root", str(repo)) == 0
    assert time.monotonic() - t0 >= 0.35
    evs = json.loads(capsys.readouterr().out)["workers"][0]["events"]
    assert evs[-1]["type"] == "completion"



def test_sync_collapses_consecutive_tool_use_lines(tmp_path: Path, capsys) -> None:
    repo, _ = make_worker_repo(tmp_path)
    rec = _idle_rec(repo)
    for _ in range(6):
        ws.append_event(repo, rec, "output", source="worker", summary="(tool use)")
    run_worker_cli("worker", "sync", "--repo-root", str(repo))
    out = capsys.readouterr().out
    assert " output: 6 tool uses" in out
    assert "-#" in out
    assert out.count("(tool use)") == 0



def test_sync_verbose_shows_each_tool_use(tmp_path: Path, capsys) -> None:
    repo, _ = make_worker_repo(tmp_path)
    rec = _idle_rec(repo)
    ws.append_event(repo, rec, "output", source="worker", summary="(tool use)")
    ws.append_event(repo, rec, "output", source="worker", summary="(tool use)")
    run_worker_cli("worker", "sync", "--verbose", "--repo-root", str(repo))
    out = capsys.readouterr().out
    assert out.count("(tool use)") == 2



def test_completion_missing_ready_offers_ready_only_resume() -> None:
    lines = sync_event_lines([], [{"seq": 3, "type": "completion", "source": "worker",
                                     "summary": "exit 0; READY file missing",
                                     "detail": {"exit": 0, "ready": False}}], "w-0001")
    assert any("worker resume w-0001 --ready-only" in line for line in lines)
