"""``worker message`` queues a follow-up while a turn is running (M11.14)."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

from tests.test_worker_cli import _repo, run_worker_cli, wait_for_worker

from specy_road import worker_ops as ops
from specy_road import worker_state as ws
from specy_road.bundled_scripts import worker_cli_render as wcr


FAKE_SLOW = '''
import json, sys, time
from pathlib import Path
prompt = Path(sys.argv[1])
turn_file = prompt.with_name(prompt.name + ".turn")
turn = int(turn_file.read_text()) if turn_file.is_file() else 0
turn_file.write_text(str(turn + 1))
lines = [
    {"type": "system", "subtype": "init", "session_id": "sid-live", "model": "fake"},
    {"type": "result", "subtype": "success", "result": "done", "session_id": "sid-live"},
]
time.sleep(2 if turn == 0 else 0)
for d in lines:
    print(json.dumps(d), flush=True)
sys.exit(0)
'''


def _slow_repo(tmp_path: Path) -> Path:
    script = tmp_path / "slow.py"
    script.write_text(FAKE_SLOW)
    from tests.test_worker_cli import worker_roster
    from tests.review_repo_helpers import git, make_review_repo

    repo = make_review_repo(tmp_path, orchestration=worker_roster(f"{sys.executable} {script} {{prompt}} {{session}}"))
    (repo / ".gitignore").write_text("work/\n")
    git(repo, "add", ".gitignore")
    git(repo, "commit", "-qm", "ignore work")
    return repo


def test_message_while_running_queues_and_delivers(tmp_path: Path, capsys) -> None:
    repo = _slow_repo(tmp_path)
    rec, _ = ops.delegate(repo, "M1.1", "opus")
    for _ in range(100):
        if ws.load_record(repo, rec.worker_id).pid is not None:
            break
        time.sleep(0.05)
    else:
        raise AssertionError("worker never started")
    assert run_worker_cli("worker", "message", rec.worker_id, "--text", "follow up", "--repo-root", str(repo)) == 0
    assert "message queued for the next turn" in capsys.readouterr().out
    queued = ws.load_record(repo, rec.worker_id)
    assert queued.queued_message == "follow up"
    assert "message_queued" in [e.type for e in ws.events_since(repo, rec.worker_id)]
    deadline = time.time() + 30
    while time.time() < deadline:
        types = [e.type for e in ws.events_since(repo, rec.worker_id)]
        if types.count("completion") >= 2:
            final = ws.load_record(repo, rec.worker_id)
            break
        time.sleep(0.1)
    else:
        raise AssertionError("queued message was not delivered as a second turn")
    assert final.queued_message is None and final.state == "idle"
    types = [e.type for e in ws.events_since(repo, rec.worker_id)]
    assert "message" in types and types.count("resumed") >= 1
    prompt = next(p for p in (repo / "work").glob(f"prompt-{rec.worker_id}-message-*.md") if "follow up" in p.read_text())
    assert prompt.is_file()


def test_no_queue_refuses_a_live_turn(tmp_path: Path, monkeypatch) -> None:
    repo, _ = _repo(tmp_path)
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    ws.mutate(repo, rec, lambda r: setattr(r, "provider_session_id", "sid-1"))
    ws.set_state(repo, rec, "running", pid=None)
    monkeypatch.setattr(ops, "wrapper_gone", lambda *_a: False)
    monkeypatch.setattr(ops, "process_alive", lambda *_a: True)
    with pytest.raises(ws.WorkerError, match="cannot steer a live turn"):
        ops.message(repo, rec.worker_id, "x", no_queue=True)


def test_list_and_sync_show_queued_message(tmp_path: Path, capsys) -> None:
    repo, _ = _repo(tmp_path)
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    ws.mutate(repo, rec, lambda r: (setattr(r, "provider_session_id", "sid-1"), setattr(r, "queued_message", "wait for it")))
    ws.set_state(repo, rec, "running", pid=None)
    line = wcr._line(ws.load_record(repo, rec.worker_id), repo)
    assert "queued: wait for it" in line
    ws.append_event(repo, rec, "message_queued", source="orchestrator", authority="orchestrator", summary="queued: wait")
    assert run_worker_cli("worker", "sync", "--repo-root", str(repo), "--json") == 0
    out = json.loads(capsys.readouterr().out)
    assert out["workers"][0].get("queued_message") == "wait for it"


def test_terminate_drops_queued_message(tmp_path: Path) -> None:
    repo, _ = _repo(tmp_path)
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    ws.mutate(repo, rec, lambda r: setattr(r, "provider_session_id", "sid-1"))
    ws.set_state(repo, rec, "running", pid=None)
    ws.mutate(repo, rec, lambda r: setattr(r, "queued_message", "never sent"))
    assert run_worker_cli("worker", "terminate", rec.worker_id, "--repo-root", str(repo)) == 0
    assert ws.load_record(repo, rec.worker_id).queued_message is None
    summary = ws.events_since(repo, rec.worker_id)[-1].summary
    assert "dropped queued follow-up" in summary
