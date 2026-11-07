"""Stalled workers: detected from launch, shown everywhere, recovered in one bounded command (M22.39)."""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from tests.review_repo_helpers import git, make_review_repo
from tests.worker_cli_helpers import run_worker_cli, wait_for_worker
from tests.worker_repo_helpers import make_worker_repo, worker_roster

from specy_road import worker_adapters as wa
from specy_road import worker_ops as ops
from specy_road import worker_ops_slots as slots
from specy_road import worker_runner as wr
from specy_road import worker_state as ws
from specy_road.bundled_scripts import doctor
from specy_road.worker_process import wrapper_alive

OLD = "2026-01-01T00:00:00+00:00"   # long past policy.stall_after_seconds (default 600)


def _running(repo: Path, **fields) -> ws.WorkerRecord:
    """A ``running`` record on M1.1 with no process behind it: refusals happen before any process is touched."""
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    ws.mutate(repo, rec, lambda r: r.__dict__.update(state="running", **fields))
    return ws.load_record(repo, rec.worker_id)


def _repo(tmp_path: Path, policy: str) -> Path:
    """A review repo whose committed policy adds ``policy`` (read from the integration branch)."""
    return make_review_repo(tmp_path, orchestration=worker_roster("harness {prompt}").replace(
        "policy: {max_workers: 2}", f"policy: {{max_workers: 2, {policy}}}"))


def test_a_worker_that_never_wrote_output_is_flagged_from_its_launch(tmp_path: Path, capsys) -> None:
    repo = _repo(tmp_path, "stall_after_seconds: 1")
    rec = _running(repo)   # last_output_at never written: the harness has not started
    launched = datetime.fromisoformat(ws.events_since(repo, rec.worker_id)[0].at)
    assert ops.sweep_stalled(repo, now=launched) == []
    assert [r.worker_id for r in ops.sweep_stalled(repo, now=launched + timedelta(seconds=1))] == [rec.worker_id]
    [s] = slots.stalled_workers(repo, now=launched + timedelta(seconds=700))
    assert s["silent_seconds"] == 700 and s["recoveries"] == 0 and not s["needs_person"]
    # list and doctor name it with how long it has been silent, measured now (sync: a live worker, below).
    time.sleep(1.1)
    assert run_worker_cli("worker", "list", "--repo-root", str(repo)) == 0
    assert f"stalled: {rec.worker_id} (M1.1) silent " in capsys.readouterr().out
    with pytest.raises(SystemExit):
        doctor.main(["--repo-root", str(repo)])
    out = capsys.readouterr().out
    assert "Stalled workers" in out and f"{rec.worker_id} (M1.1) silent " in out


def test_recover_ends_a_stalled_worker_keeps_its_work_and_resumes(tmp_path: Path, capsys) -> None:
    repo, script = make_worker_repo(tmp_path)
    spec = tmp_path / "silent.json"
    spec.write_text(json.dumps({"lines": [{"type": "system", "subtype": "init", "session_id": "quiet"}], "sleep": 60}))
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    wr.spawn(repo, rec, wa.Launch([sys.executable, str(script), str(spec)]))
    try:
        for _ in range(100):
            if ws.load_record(repo, rec.worker_id).provider_session_id:
                break
            time.sleep(0.1)
        # Output within the window: not stalled, so recover leaves the working worker running.
        assert run_worker_cli("worker", "recover", rec.worker_id, "--repo-root", str(repo)) == 1
        assert "not stalled" in capsys.readouterr().err
        busy = ws.load_record(repo, rec.worker_id)
        assert wrapper_alive(busy, repo) and not busy.recoveries
        # The worker's work: a commit and an uncommitted file in its worktree.
        (repo / "done.txt").write_text("committed\n")
        git(repo, "add", "done.txt")
        git(repo, "commit", "-qm", "worker commit")
        head = git(repo, "rev-parse", "HEAD")
        (repo / "wip.txt").write_text("uncommitted\n")
        ws.mutate(repo, rec, lambda r: setattr(r, "last_output_at", OLD))
        assert run_worker_cli("worker", "sync", "--json", "--repo-root", str(repo)) == 0
        [stalled] = json.loads(capsys.readouterr().out)["stalled"]
        assert stalled["worker_id"] == rec.worker_id and stalled["silent_seconds"] >= 600
        assert run_worker_cli("worker", "recover", rec.worker_id, "--repo-root", str(repo)) == 0
        assert "recovered" in capsys.readouterr().out
        assert not wrapper_alive(busy, repo)   # the stalled turn was ended
        after = wait_for_worker(repo, rec.worker_id, timeout=30)
        assert after.state == "idle" and after.recoveries == 1 and ws.FLAG_STALLED not in after.flags
        assert [e.type for e in ws.events_since(repo, rec.worker_id)].count("resumed") == 1
        assert git(repo, "rev-parse", "HEAD") == head and (repo / "wip.txt").read_text() == "uncommitted\n"
    finally:
        if ws.load_record(repo, rec.worker_id).state != "terminated":
            ops.terminate(repo, rec.worker_id)


def test_recover_past_the_limit_stops_as_needing_a_person(tmp_path: Path) -> None:
    repo = _repo(tmp_path, "max_fix_rounds: 2")
    rec = _running(repo, last_output_at=OLD, recoveries=2, provider_session_id="quiet")   # two recover calls so far
    ws.append_event(repo, rec, "output", source="worker", authority="worker_suggestion", summary="Bash: pytest -x")
    # grind-session's loop runs the same recovery.
    [r] = slots.recover_stalled(repo)
    assert r["outcome"] == "needs_person" and "Bash: pytest -x" in r["detail"]
    with pytest.raises(ws.WorkerError, match="needs a person.*Bash: pytest -x"):
        slots.recover(repo, rec.worker_id)
    after = ws.load_record(repo, rec.worker_id)
    assert after.state == "running" and after.recoveries == 2 and ws.FLAG_NEEDS_PERSON in after.flags
    assert len([e for e in ws.events_since(repo, rec.worker_id) if "needs a person" in e.summary]) == 1
    assert slots.recover_stalled(repo) == []   # already waiting for a person: not retried


def test_recover_refuses_while_another_worker_holds_the_leaf(tmp_path: Path) -> None:
    repo, _ = make_worker_repo(tmp_path)
    stalled = _running(repo, last_output_at=OLD, provider_session_id="quiet")
    other = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    ws.set_state(repo, other, "idle")
    with pytest.raises(ws.WorkerError, match=f"already has an active worker \\({other.worker_id}"):
        slots.recover(repo, stalled.worker_id)
    after = ws.load_record(repo, stalled.worker_id)
    assert after.state == "running" and not after.recoveries
