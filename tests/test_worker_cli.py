"""``specy-road worker``: delegate, sync, leases, handoff/reclaim, hook, reconcile (slice 7c)."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

from tests.review_repo_helpers import git, make_review_repo

from specy_road import worker_ops as ops
from specy_road import worker_state as ws
from specy_road.bundled_scripts import review_cli, worker_cli

FAKE = '''
import json, sys, time
spec = json.loads(open(sys.argv[1]).read()) if sys.argv[1].endswith(".json") else {"lines": [
    {"type": "system", "subtype": "init", "session_id": "s-" + str(len(sys.argv)), "model": "fake"},
    {"type": "result", "subtype": "success", "result": "done", "session_id": "s-" + str(len(sys.argv))}]}
if spec.get("write"):                       # a READY written during the turn, as a real harness would
    open(spec["write"]["path"], "w").write(spec["write"]["text"])
for d in spec["lines"]:
    print(json.dumps(d), flush=True)
time.sleep(spec.get("sleep", 0))
sys.exit(spec.get("exit", 0))
'''


def worker_roster(cli: str, *, max_workers: int = 2) -> str:
    return (f"version: 1\nroster:\n  - {{id: human, family: human, roles: [coordinator, reviewer]}}\n"
            f"  - {{id: opus, family: anthropic, roles: [executor, reviewer], harness: claude-code,\n"
            f"     billing_route: claude_subscription, channels: {{cli: '{cli}'}}}}\n"
            f"  - {{id: sol, family: openai, roles: [reviewer]}}\n"
            f"policy: {{max_workers: {max_workers}}}\n")


def _repo(tmp_path: Path, *, max_workers: int = 2) -> tuple[Path, Path]:
    script = tmp_path / "fake.py"
    script.write_text(FAKE)
    repo = make_review_repo(tmp_path, orchestration=worker_roster(f"{sys.executable} {script} {{prompt}} {{session}}", max_workers=max_workers))
    (repo / ".gitignore").write_text("work/\n")
    git(repo, "add", ".gitignore")
    git(repo, "commit", "-qm", "ignore work")
    return repo, script


def run_worker_cli(*args: str) -> int:
    with pytest.raises(SystemExit) as e:
        worker_cli.main(list(args))
    return e.value.code or 0


def wait_for_worker(repo: Path, wid: str, timeout: float = 10) -> ws.WorkerRecord:
    for _ in range(int(timeout * 10)):
        rec = ws.load_record(repo, wid)
        if rec.pid is None:
            return rec
        time.sleep(0.1)
    raise AssertionError("worker did not finish")


def test_delegate_returns_at_once_and_is_idempotent(tmp_path: Path, capsys) -> None:
    repo, _ = _repo(tmp_path)
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
    repo, _ = _repo(tmp_path, max_workers=1)
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
    repo, _ = _repo(tmp_path)
    assert run_worker_cli("worker", "delegate", "M1.1", "--model", "opus", "--op-id", "op-1", "--json", "--repo-root", str(repo)) == 0
    first = json.loads(capsys.readouterr().out)
    wait_for_worker(repo, first["worker_id"])
    assert run_worker_cli("worker", "delegate", "M1.1", "--model", "opus", "--op-id", "op-1", "--json", "--repo-root", str(repo)) == 0
    assert json.loads(capsys.readouterr().out) == first


def test_sync_delta_and_ack(tmp_path: Path, capsys) -> None:
    repo, _ = _repo(tmp_path)
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


def test_message_resume_lease_and_interrupt(tmp_path: Path, capsys) -> None:
    repo, _ = _repo(tmp_path)
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
    repo, _ = _repo(tmp_path)
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
    repo, _ = _repo(tmp_path)
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
    git(repo, "add", "-f", "work/notes.md")
    git(repo, "commit", "-qm", "worker notes")
    assert run_worker_cli("worker", "reconcile", "w-0001", "--repo-root", str(repo)) == 0
    out = capsys.readouterr().out
    assert "OUTSIDE touch zones: README.md" in out and "OUTSIDE touch zones: work/notes.md" in out
    assert "needs_reconcile=True" in out
    assert "brief-M1.1" not in out
    assert ws.FLAG_RECONCILE in ws.load_record(repo, "w-0001").flags


def test_terminate_a_live_worker(tmp_path: Path) -> None:
    repo, script = _repo(tmp_path)
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
    repo, _ = _repo(tmp_path)
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
