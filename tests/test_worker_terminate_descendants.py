"""``worker terminate`` also ends what the harness started in a session of its own (M21.29, D6).

Cursor's shell tool runs each command as a new session leader, so ``killpg`` on
the worker's group never reaches it. ``kill_group`` lists the group's
descendants outside it before the first signal and signals each one whose start
time still matches with the group (M22.20); a zombie is no survivor, and a failed
listing is repeated by the next ``terminate``.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from specy_road import worker_state as ws
from specy_road.worker_adapters import Launch
from specy_road.worker_process import kill_group, start_token
from specy_road.worker_runner import spawn
from specy_road.worker_state import WorkerError

from tests.worker_cli_helpers import run_worker_cli
from tests.worker_repo_helpers import make_worker_repo

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX process groups and sessions")

#: A harness whose child leaves the group (``os.setsid``), writes its pid to a ready file, and sleeps.
HARNESS = '''
import subprocess, sys, time
child = """
import os, signal, sys, time
os.setsid()
if sys.argv[2] == "ignore":
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
open(sys.argv[1] + ".tmp", "w").write(str(os.getpid()))
os.replace(sys.argv[1] + ".tmp", sys.argv[1])
time.sleep(120)
"""
subprocess.Popen([sys.executable, "-c", child, sys.argv[1], sys.argv[2]])
print('{"type": "system", "subtype": "init", "session_id": "escaped"}', flush=True)
time.sleep(120)
'''

INVENTORY = ["ps", "-A", "-ww", "-o", "pid=,ppid=,pgid=,stat=,lstart="]
FAKE_PID = 4_194_000   # above any default pid_max: no real process is ever signalled through it


def _gone(pid: int, wait: float = 5.0) -> bool:
    """No process ``pid`` (or only a zombie) within ``wait`` seconds."""
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:
        stat = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True).stdout.strip()
        if not stat or stat.startswith("Z"):
            return True
        time.sleep(0.1)
    return False


def _kill(pid: int | None) -> None:
    if pid:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass


@pytest.mark.parametrize("child_mode", ["default", "ignore"])
def test_terminate_ends_a_grandchild_in_its_own_session(tmp_path: Path, child_mode: str) -> None:
    repo, _ = make_worker_repo(tmp_path)
    harness = tmp_path / "escaping_harness.py"
    harness.write_text(HARNESS)
    ready = tmp_path / "grandchild.pid"
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    wrapper = grandchild = None
    try:
        wrapper = spawn(repo, rec, Launch([sys.executable, str(harness), str(ready), child_mode]))
        for _ in range(100):
            if ready.is_file() and ws.load_record(repo, rec.worker_id).harness_pid:
                break
            time.sleep(0.1)
        grandchild = int(ready.read_text())
        pgid = ws.load_record(repo, rec.worker_id).pgid
        assert os.getpgid(grandchild) != pgid   # it left the group, so killpg alone misses it
        if child_mode == "ignore":   # SIGTERM ignored: SIGKILL after the explicit short grace
            kill_group(ws.load_record(repo, rec.worker_id), repo, grace=0.5)
        else:
            assert run_worker_cli("worker", "terminate", rec.worker_id, "--repo-root", str(repo)) == 0
            assert ws.load_record(repo, rec.worker_id).state == "terminated"
        assert _gone(grandchild)
        assert _gone(wrapper) and not subprocess.run(["ps", "-A", "-o", "pgid="], capture_output=True, text=True
                                                     ).stdout.split().count(str(pgid))
    finally:
        _kill(grandchild)
        _kill(wrapper)


@pytest.fixture
def leader(tmp_path: Path):
    """A real sleeping session leader recorded as a worker's harness, with no wrapper.

    Started through a parent that exits at once, so init reaps it and no zombie of ours stays in its group.
    """
    starter = ("import subprocess, sys; print(subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'], "
               "stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True).pid)")
    pid = int(subprocess.run([sys.executable, "-c", starter], capture_output=True, text=True, check=True).stdout)
    try:
        for _ in range(50):
            if start := start_token(pid):
                break
            time.sleep(0.1)
        yield pid, ws.WorkerRecord(
            worker_id="w-0009", node_id="M1.1", harness="cursor", model="m", worktree=str(tmp_path), state="running",
            lease={}, instruction_epoch=0, attempt=0, last_event_seq=0, created="", updated="",
            pgid=pid, harness_pid=pid, harness_start=start)
    finally:
        _kill(pid)


def _seams(monkeypatch, leader_pid: int, *, before: str | None, after: str | None, stat: str = "S",
           dies: bool = False, outage: dict[str, int] | None = None) -> list[tuple[int, int]]:
    """Patch ``ps`` and ``os.kill``: a fake descendant of ``leader_pid`` outside its group.

    The inventory lists it started at ``before`` and every later read at ``after`` in state ``stat`` (``None``: not
    listed); a ``before`` of ``None`` makes the first inventory unreadable, and while ``outage["on"]`` every read
    after the first ``outage["ok"]`` fails. ``dies``: no longer listed once signalled. Returns the signals sent to the fake pid.
    """
    real_run, real_kill, sent, reads = subprocess.run, os.kill, [], []

    def run(args, *a, **kw):
        r = real_run(args, *a, **kw)
        if list(args) != INVENTORY:
            return r
        first = not reads
        reads.append(args)
        if (first and before is None) or (outage and outage["on"] and len(reads) > outage["ok"]):
            return subprocess.CompletedProcess(args, 1, "", "ps: unreadable")
        start = None if dies and sent else before if first else after
        row = f"{FAKE_PID} {leader_pid} {FAKE_PID} {'S' if first else stat} {start}\n" if start else ""
        return subprocess.CompletedProcess(args, 0, r.stdout + row, "")

    def kill(pid, sig):
        if pid == FAKE_PID:
            sent.append((pid, sig))
            return None
        return real_kill(pid, sig)

    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(os, "kill", kill)
    return sent


def test_a_descendant_whose_start_time_changed_is_neither_signalled_nor_a_survivor(leader, monkeypatch) -> None:
    pid, rec = leader
    sent = _seams(monkeypatch, pid, before="Thu Nov  5 10:00:00 2026", after="Thu Nov  5 10:00:09 2026")
    kill_group(rec, grace=0.5)
    assert sent == [] and _gone(pid)


def test_an_unreadable_inventory_raises_after_the_group_is_signalled(leader, monkeypatch) -> None:
    pid, rec = leader
    _seams(monkeypatch, pid, before=None, after=None)
    with pytest.raises(WorkerError, match="could not list its descendants"):
        kill_group(rec, grace=0.5)
    assert _gone(pid)   # the group itself was still ended


@pytest.mark.parametrize("stat", ["S", "Z"], ids=["running", "zombie-kept-by-a-subreaper"])
def test_a_same_start_survivor_raises_naming_its_pid(leader, monkeypatch, stat: str) -> None:
    """A zombie (its subreaper never waits for it) is gone, not a survivor (M22.20): terminate succeeds."""
    pid, rec = leader
    start = "Thu Nov  5 10:00:00 2026"
    sent = _seams(monkeypatch, pid, before=start, after=start, stat=stat)
    if stat == "Z":
        kill_group(rec, grace=0.3)
    else:
        with pytest.raises(WorkerError, match=f"{FAKE_PID}.*still alive after SIGKILL"):
            kill_group(rec, grace=0.3)
        assert {s for _, s in sent} == {signal.SIGTERM, signal.SIGKILL}
    assert _gone(pid)


@pytest.mark.parametrize("ok", [0, 1], ids=["every-listing-fails", "fails-after-the-snapshot"])
def test_a_failed_inventory_is_repeated_by_the_next_terminate(tmp_path: Path, leader, monkeypatch, ok: int) -> None:
    """M22.20: a listing that fails at any step of the first terminate keeps ``descendants_unchecked`` and the record
    not terminated; the second lists the descendant (its parent link to the recorded harness still holds), signals
    it and clears the mark."""
    pid, fixture = leader
    repo, _ = make_worker_repo(tmp_path)
    rec = ws.create_record(repo, "M1.1", "cursor", "m", repo)
    ws.mutate(repo, rec, lambda r: r.__dict__.update(state="running", pgid=pid, harness_pid=pid,
                                                     harness_start=fixture.harness_start))
    start, outage = "Thu Nov  5 10:00:00 2026", {"on": True, "ok": ok}
    sent = _seams(monkeypatch, pid, before=start, after=start, dies=True, outage=outage)
    assert run_worker_cli("worker", "terminate", rec.worker_id, "--repo-root", str(repo)) != 0
    first = ws.load_record(repo, rec.worker_id)
    assert first.state == "running" and first.descendants_unchecked is True
    assert sent == [] and _gone(pid)   # the group was ended; its descendant was never listed
    outage["on"] = 0
    assert run_worker_cli("worker", "terminate", rec.worker_id, "--repo-root", str(repo)) == 0
    second = ws.load_record(repo, rec.worker_id)
    assert second.state == "terminated" and not second.descendants_unchecked
    assert sent == [(FAKE_PID, signal.SIGTERM)]


#: A harness that ignores SIGTERM (so the group's grace runs out) with a child in a session of its own. The child
#: records when SIGTERM reaches it and only then forks: the fork comes after the snapshot, inside the group's grace.
FORKING = '''
import signal, subprocess, sys, time
signal.signal(signal.SIGTERM, signal.SIG_IGN)
child = """
import os, signal, sys, time
os.setsid()
def term(*_):
    open(sys.argv[1] + ".term", "w").write(repr(time.time()))
    if os.fork() == 0:
        open(sys.argv[1] + ".fork", "w").write(str(os.getpid()))
        time.sleep(120)
        os._exit(0)
signal.signal(signal.SIGTERM, term)
open(sys.argv[1] + ".tmp", "w").write(str(os.getpid()))
os.replace(sys.argv[1] + ".tmp", sys.argv[1])
while True:
    time.sleep(1)
"""
subprocess.Popen([sys.executable, "-c", child, sys.argv[1]])
print('{"type": "system", "subtype": "init", "session_id": "forking"}', flush=True)
time.sleep(120)
'''


def test_an_escaped_child_gets_sigterm_with_the_group_not_after_its_grace(tmp_path: Path) -> None:
    repo, _ = make_worker_repo(tmp_path)
    harness = tmp_path / "forking_harness.py"
    harness.write_text(FORKING)
    ready = tmp_path / "escaped.pid"
    term_at, fork_file = Path(f"{ready}.term"), Path(f"{ready}.fork")
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    wrapper = escaped = forked = None
    try:
        wrapper = spawn(repo, rec, Launch([sys.executable, str(harness), str(ready)]))
        for _ in range(100):
            if ready.is_file() and ws.load_record(repo, rec.worker_id).harness_pid:
                break
            time.sleep(0.1)
        escaped = int(ready.read_text())
        assert os.getpgid(escaped) != ws.load_record(repo, rec.worker_id).pgid
        assert not fork_file.exists()   # nothing forked before the snapshot
        began = time.time()
        kill_group(ws.load_record(repo, rec.worker_id), repo, grace=3.0)   # no survivor: no WorkerError
        for _ in range(50):
            if fork_file.is_file() and fork_file.read_text():
                break
            time.sleep(0.1)
        forked = int(fork_file.read_text())
        assert float(term_at.read_text()) - began < 2.0   # with the group's SIGTERM, inside its 3 s grace
        assert forked != escaped and _gone(escaped)
        assert _gone(forked)   # forked during the grace by a listed descendant: found at the next step, no survivor
    finally:
        _kill(forked)
        _kill(escaped)
        _kill(wrapper)
