"""``worker message`` queues a follow-up while a turn is running (M11.14)."""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path

import pytest

from tests.review_repo_helpers import git, make_review_repo
from tests.test_worker_cli import run_worker_cli, wait_for_worker
from tests.worker_lease_helpers import remote_and_clone
from tests.worker_repo_helpers import make_worker_repo, worker_roster

from specy_road import worker_ops as ops
from specy_road import worker_runner as wr
from specy_road import worker_state as ws
from specy_road.bundled_scripts import review_cli
from specy_road.worker_adapters import Launch
from specy_road.worker_runner_ready import READY_ONLY_PROMPT


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
    # worker_runner writes the completion event before _exit_state clears running → idle.
    while time.time() < deadline:
        types = [e.type for e in ws.events_since(repo, rec.worker_id)]
        final = ws.load_record(repo, rec.worker_id)
        if types.count("completion") >= 2 and final.state != "running":
            break
        time.sleep(0.1)
    else:
        raise AssertionError("queued message was not delivered as a second turn")
    assert final.queued_message is None and final.state == "idle"
    types = [e.type for e in ws.events_since(repo, rec.worker_id)]
    assert "message" in types and types.count("resumed") >= 1
    prompt = next(p for p in (repo / "work").glob(f"prompt-{rec.worker_id}-message-*.md") if "follow up" in p.read_text())
    assert prompt.is_file()


def test_two_cli_messages_during_a_live_turn_are_appended_and_delivered(tmp_path: Path, capsys) -> None:
    repo = _slow_repo(tmp_path)
    rec, _ = ops.delegate(repo, "M1.1", "opus")
    for _ in range(100):
        if ws.load_record(repo, rec.worker_id).pid is not None:
            break
        time.sleep(0.05)
    else:
        raise AssertionError("worker never started")
    assert run_worker_cli("worker", "message", rec.worker_id, "--text", "first follow-up", "--repo-root", str(repo)) == 0
    assert "message queued for the next turn" in capsys.readouterr().out
    assert run_worker_cli("worker", "message", rec.worker_id, "--text", "second follow-up", "--repo-root", str(repo)) == 0
    assert "message queued for the next turn" in capsys.readouterr().out
    assert ws.load_record(repo, rec.worker_id).queued_message == "first follow-up\n\nsecond follow-up"
    summaries = [e.summary for e in ws.events_since(repo, rec.worker_id) if e.type == "message_queued"]
    assert any(s.startswith("queued: first follow-up") for s in summaries)
    assert any(s.startswith("appended: second follow-up") for s in summaries)
    deadline = time.time() + 30
    while time.time() < deadline:
        if [e.type for e in ws.events_since(repo, rec.worker_id)].count("completion") >= 2:
            break
        time.sleep(0.1)
    else:
        raise AssertionError("queued messages were not delivered as a second turn")
    delivered = "first follow-up\n\nsecond follow-up"
    prompt = next(p for p in (repo / "work").glob(f"prompt-{rec.worker_id}-message-*.md") if p.read_text() == delivered)
    assert prompt.is_file()


def test_no_queue_refuses_a_live_turn(tmp_path: Path, monkeypatch) -> None:
    repo, _ = make_worker_repo(tmp_path)
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    ws.mutate(repo, rec, lambda r: setattr(r, "provider_session_id", "sid-1"))
    ws.set_state(repo, rec, "running", pid=None)
    monkeypatch.setattr(ops, "wrapper_gone", lambda *_a: False)
    monkeypatch.setattr(ops, "process_alive", lambda *_a: True)
    with pytest.raises(ws.WorkerError, match="cannot steer a live turn"):
        ops.message(repo, rec.worker_id, "x", no_queue=True)


def test_list_and_sync_show_queued_message(tmp_path: Path, capsys) -> None:
    repo, _ = make_worker_repo(tmp_path)
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    ws.mutate(repo, rec, lambda r: (setattr(r, "provider_session_id", "sid-1"), setattr(r, "queued_message", "wait for it")))
    ws.set_state(repo, rec, "running", pid=None)
    assert run_worker_cli("worker", "list", "--repo-root", str(repo)) == 0
    assert "queued: wait for it" in capsys.readouterr().out
    ws.append_event(repo, rec, "message_queued", source="orchestrator", authority="orchestrator", summary="queued: wait")
    assert run_worker_cli("worker", "sync", "--repo-root", str(repo), "--json") == 0
    out = json.loads(capsys.readouterr().out)
    assert out["workers"][0].get("queued_message") == "wait for it"


def test_terminate_drops_queued_message(tmp_path: Path) -> None:
    repo, _ = make_worker_repo(tmp_path)
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    ws.mutate(repo, rec, lambda r: setattr(r, "provider_session_id", "sid-1"))
    ws.set_state(repo, rec, "running", pid=None)
    ws.mutate(repo, rec, lambda r: setattr(r, "queued_message", "never sent"))
    assert run_worker_cli("worker", "terminate", rec.worker_id, "--repo-root", str(repo)) == 0
    assert ws.load_record(repo, rec.worker_id).queued_message is None
    summary = ws.events_since(repo, rec.worker_id)[-1].summary
    assert "dropped queued follow-up" in summary


def test_deliver_and_message_launch_one_turn(tmp_path: Path, monkeypatch) -> None:
    repo, _ = make_worker_repo(tmp_path)
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    ws.mutate(repo, rec, lambda r: setattr(r, "provider_session_id", "sid-1"))
    ws.set_state(repo, rec, "idle", pid=None)
    ws.mutate(repo, rec, lambda r: setattr(r, "queued_message", "queued-follow-up"))
    spawned: list[str] = []
    gate = threading.Event()

    def fake_spawn(repo_root, r, launch, *, resumed=False):
        spawned.append(r.worker_id)
        gate.wait(1)
        ws.set_state(repo_root, r, "running", pid=os.getpid())
        return os.getpid()

    monkeypatch.setattr(ops, "spawn", fake_spawn)
    monkeypatch.setattr(ops, "process_alive", lambda r, repo_root=None: r.pid == os.getpid())
    monkeypatch.setattr(ops, "wrapper_gone", lambda repo_root, r: False)
    errors: list[Exception] = []

    def deliver() -> None:
        try:
            wr.deliver_queued_message(repo, rec.worker_id)
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    def send() -> None:
        try:
            ops.message(repo, rec.worker_id, "from-coordinator")
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=deliver), threading.Thread(target=send)]
    for t in threads:
        t.start()
    time.sleep(0.2)
    gate.set()
    for t in threads:
        t.join()
    assert len(spawned) == 1 and len(errors) == 0
    left = ws.load_record(repo, rec.worker_id).queued_message
    sent = next(p for p in (repo / "work").glob(f"prompt-{rec.worker_id}-message-*.md") if p.is_file()).read_text()
    if sent == "queued-follow-up\n\nfrom-coordinator":   # message launched and took the queued text with it
        assert left is None
    else:
        assert sent == "queued-follow-up" and left == "from-coordinator"   # deliver launched; the message queued


_STORED = "stored follow-up"

# Holds the turn open until the test has queued both follow-ups. argv is the delegate prompt; the gate is a sibling file.
_GATED = '''
import json, sys, time
from pathlib import Path
gate = Path("work/release-turn")
deadline = time.time() + 30
while not gate.is_file():
    if time.time() > deadline:
        sys.exit(1)
    time.sleep(0.05)
print(json.dumps({"type": "result", "subtype": "success", "result": "done", "session_id": "sid-live"}), flush=True)
'''


def _reject_leases(remote: Path) -> None:
    """The remote stays readable and refuses every lease ref push."""
    hook = remote / "hooks" / "update"
    hook.write_text('#!/bin/sh\ncase "$1" in refs/specy-road/*) echo "no leases here" >&2; exit 1;; esac\nexit 0\n')
    hook.chmod(0o755)


def _block_prompt_writes(repo: Path, wid: str) -> None:
    """``work/prompt-<id>-message-N.md`` is a directory, so the delivery write raises OSError."""
    work = repo / "work"
    work.mkdir(exist_ok=True)
    for n in range(1, 40):
        (work / f"prompt-{wid}-message-{n}.md").mkdir()


def _deliver_fail(tmp_path: Path, *, harness: str = "claude-code", reject: bool = False,
                  block: bool = False) -> tuple[Path, str, int]:
    """One fake turn with a queued follow-up. Returns ``(repo, worker id, wrapper exit)``."""
    repo, script = make_worker_repo(tmp_path)
    if reject:
        remote, _clone = remote_and_clone(tmp_path, repo)
        _reject_leases(remote)
    rec = ws.create_record(repo, "M1.1", harness, "opus", repo)
    ws.mutate(repo, rec, lambda r: (setattr(r, "provider_session_id", "sid-live"),
                                    setattr(r, "queued_message", _STORED)))
    if block:
        _block_prompt_writes(repo, rec.worker_id)
    spec = tmp_path / "turn.json"
    spec.write_text(json.dumps({"lines": [
        {"type": "result", "subtype": "success", "result": "done", "session_id": "sid-live"}], "exit": 0}))
    code = wr.run(repo, rec.worker_id, Launch([sys.executable, str(script), str(spec)]))
    return repo, rec.worker_id, code


def _flags(repo: Path, wid: str, capsys) -> None:
    root = str(repo)
    assert run_worker_cli("worker", "list", "--json", "--repo-root", root) == 0
    listed = json.loads(capsys.readouterr().out)["workers"]
    assert run_worker_cli("worker", "status", wid, "--json", "--repo-root", root) == 0
    status = json.loads(capsys.readouterr().out)
    with pytest.raises(SystemExit) as caught:
        review_cli.main(["handoff", "status", "--json", "--repo-root", root])
    assert (caught.value.code or 0) == 0
    handoff = json.loads(capsys.readouterr().out)["workers"]
    assert listed and listed[0]["worker_id"] == wid and handoff and handoff[0]["worker_id"] == wid
    for flags in (listed[0]["flags"], status["flags"], handoff[0]["flags"]):
        assert ws.FLAG_UNDELIVERED in flags


def _stuck(repo: Path, wid: str, text: str, capsys) -> None:
    assert ws.load_record(repo, wid).queued_message == text
    assert [e.type for e in ws.events_since(repo, wid)].count("error") == 1
    _flags(repo, wid, capsys)


def _prompt_text(repo: Path, wid: str, kind: str) -> str:
    files = [p for p in (repo / "work").glob(f"prompt-{wid}-{kind}-*.md") if p.is_file()]
    assert len(files) == 1
    return files[0].read_text(encoding="utf-8")


def _two_while_running(tmp_path: Path, capsys) -> None:
    """Two messages during a live turn stay in order when delivery is then refused."""
    script = tmp_path / "gated.py"
    script.write_text(_GATED)
    repo = make_review_repo(tmp_path, orchestration=worker_roster(f"{sys.executable} {script} {{prompt}} {{session}}"))
    (repo / ".gitignore").write_text("work/\n")
    git(repo, "add", ".gitignore")
    git(repo, "commit", "-qm", "ignore work")
    remote, _clone = remote_and_clone(tmp_path, repo)
    _reject_leases(remote)
    root = str(repo)
    assert run_worker_cli("worker", "delegate", "M1.1", "--model", "opus", "--offline", "--json", "--repo-root", root) == 0
    wid = json.loads(capsys.readouterr().out)["worker_id"]
    for _ in range(100):
        if ws.load_record(repo, wid).pid is not None:
            break
        time.sleep(0.05)
    else:
        raise AssertionError("worker never started")
    assert run_worker_cli("worker", "message", wid, "--text", "one", "--repo-root", root) == 0
    assert run_worker_cli("worker", "message", wid, "--text", "two", "--repo-root", root) == 0
    capsys.readouterr()
    (repo / "work" / "release-turn").write_text("go", encoding="utf-8")
    deadline = time.time() + 30
    while time.time() < deadline:
        final = ws.load_record(repo, wid)
        if final.pid is None and ws.FLAG_UNDELIVERED in final.flags:
            break
        time.sleep(0.1)
    else:
        raise AssertionError("queued text was not kept")
    _stuck(repo, wid, "one\n\ntwo", capsys)


@pytest.mark.parametrize("case", [
    "lease", "unsupported", "oserror", "message", "resume", "ready-only",
    "resume-rejected", "two-queued", "terminate",
])
def test_undelivered_queued_message(tmp_path: Path, capsys, case: str) -> None:
    if case == "two-queued":
        _two_while_running(tmp_path, capsys)
        return
    repo, wid, code = _deliver_fail(
        tmp_path, harness="generic" if case == "unsupported" else "claude-code",
        reject=case in ("lease", "resume-rejected"),
        block=case in ("oserror", "message", "resume", "ready-only", "terminate"))
    assert code == 0
    _stuck(repo, wid, _STORED, capsys)
    root = str(repo)
    if case in ("lease", "unsupported", "oserror"):
        return
    if case == "resume-rejected":
        assert run_worker_cli("worker", "resume", wid, "--repo-root", root) == 1
        _stuck(repo, wid, _STORED, capsys)
        return
    if case == "terminate":
        assert run_worker_cli("worker", "terminate", wid, "--repo-root", root) == 0
        rec = ws.load_record(repo, wid)
        assert rec.queued_message is None and ws.FLAG_UNDELIVERED not in rec.flags
        return
    if case == "message":
        for path in (repo / "work").glob(f"prompt-{wid}-message-*.md"):
            if path.is_dir():
                path.rmdir()
        assert run_worker_cli("worker", "message", wid, "--text", "B", "--repo-root", root) == 0
        assert _prompt_text(repo, wid, "message") == f"{_STORED}\n\nB"
    elif case == "resume":
        assert run_worker_cli("worker", "resume", wid, "--repo-root", root) == 0
        assert _prompt_text(repo, wid, "resume") == f"{_STORED}\n\n{ops.CONTINUE_PROMPT}"
    else:
        assert run_worker_cli("worker", "resume", wid, "--ready-only", "--repo-root", root) == 0
        assert _prompt_text(repo, wid, "ready-only") == f"{_STORED}\n\n{READY_ONLY_PROMPT}"
    rec = ws.load_record(repo, wid)
    assert rec.queued_message is None and ws.FLAG_UNDELIVERED not in rec.flags
    wait_for_worker(repo, wid)