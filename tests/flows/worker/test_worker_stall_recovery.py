"""Stalled workers: detected from launch, shown everywhere, recovered in one bounded command (M22.39)."""

from __future__ import annotations

import json
import os
import signal
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from tests.support.review import make_review_repo, git
from tests.support.cli import run_worker_cli
from tests.support.harness import make_worker_repo, wait_for_worker, worker_roster

from specy_road.orchestration.workers import worker_adapters as wa
from specy_road.orchestration.workers import worker_ops as ops
from specy_road.orchestration.workers import worker_ops as slots
from specy_road.orchestration.workers import worker_runner as wr
from specy_road.orchestration.workers import worker_state as ws
from specy_road.bundled_scripts import doctor
from specy_road.orchestration.guard.session_presence import current_user, list_sessions, start_session
from specy_road.orchestration.workers.worker_process import wrapper_alive
import subprocess
from specy_road.orchestration.workers import worker_reconcile as wrc
from specy_road.orchestration.workers import worker_process as wp

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


@pytest.mark.slow
def test_a_worker_that_never_wrote_output_is_flagged_from_its_launch(tmp_path: Path, capsys) -> None:
    repo = _repo(tmp_path, "stall_after_seconds: 1")
    rec = _running(repo)   # last_output_at never written: the harness has not started
    launched = datetime.fromisoformat(ws.events_since(repo, rec.worker_id)[0].at)
    assert ops.sweep_stalled(repo, now=launched) == []
    assert [r.worker_id for r in ops.sweep_stalled(repo, now=launched + timedelta(seconds=1))] == [rec.worker_id]
    [s] = slots.stalled_workers(repo, now=launched + timedelta(seconds=700))
    assert s["silent_seconds"] == 700 and s["recoveries"] == 0 and not s["needs_person"]
    # A follow-up turn's silence starts at the message that started it, not at the last turn's old output.
    ws.mutate(repo, rec, lambda r: setattr(r, "last_output_at", OLD))
    ws.append_event(repo, rec, "message", source="orchestrator", authority="orchestrator", summary="resume: continue")
    turn = datetime.fromisoformat(ws.events_since(repo, rec.worker_id)[-1].at)
    assert slots.stalled_workers(repo, now=turn) == [] and ws.FLAG_STALLED not in ws.load_record(repo, rec.worker_id).flags
    assert slots.stalled_workers(repo, now=turn + timedelta(seconds=5))[0]["silent_seconds"] == 5
    # list and doctor name it with how long it has been silent, measured now (sync: a live worker, below).
    time.sleep(1.1)
    assert run_worker_cli("worker", "list", "--repo-root", str(repo)) == 0
    assert f"stalled: {rec.worker_id} (M1.1) silent " in capsys.readouterr().out
    with pytest.raises(SystemExit):
        doctor.main(["--repo-root", str(repo)])
    out = capsys.readouterr().out
    assert "Stalled workers" in out and f"{rec.worker_id} (M1.1) silent " in out


def _silent_worker(tmp_path: Path) -> tuple[Path, ws.WorkerRecord]:
    """A worker whose harness printed its session id and then went silent for a minute, under a live wrapper."""
    repo, script = make_worker_repo(tmp_path)
    spec = tmp_path / "silent.json"
    spec.write_text(json.dumps({"lines": [{"type": "system", "subtype": "init", "session_id": "quiet"}], "sleep": 60}))
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    wr.spawn(repo, rec, wa.Launch([sys.executable, str(script), str(spec)]))
    for _ in range(100):
        if ws.load_record(repo, rec.worker_id).provider_session_id:
            break
        time.sleep(0.1)
    return repo, ws.load_record(repo, rec.worker_id)


@pytest.mark.slow
def test_recover_ends_a_stalled_worker_keeps_its_work_and_resumes(tmp_path: Path, capsys) -> None:
    repo, rec = _silent_worker(tmp_path)
    try:
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
        # The stalled turn's own presence session (as `session start` in the harness names it) and a peer's.
        own, peer = f"{current_user()}-s{busy.pgid}", f"{current_user()}-s1"
        for agent in (own, peer):
            start_session(repo, agent, paths=["src/"], worktree=repo)
        ws.mutate(repo, rec, lambda r: setattr(r, "last_output_at", OLD))
        assert run_worker_cli("worker", "sync", "--json", "--repo-root", str(repo)) == 0
        [stalled] = json.loads(capsys.readouterr().out)["stalled"]
        assert stalled["worker_id"] == rec.worker_id and stalled["silent_seconds"] >= 600
        assert run_worker_cli("worker", "recover", rec.worker_id, "--json", "--repo-root", str(repo)) == 0
        assert "stalled" not in json.loads(capsys.readouterr().out)["flags"]   # the resumed turn starts unflagged
        assert not wrapper_alive(busy, repo)   # the stalled turn was ended, and its presence session with it
        assert {s.agent for s in list_sessions(repo)} == {peer}
        # A second recover queued behind the first, before the new wrapper writes its launch time, finds no stall:
        # it neither ends the fresh turn nor spends a retry.
        ws.mutate(repo, rec, lambda r: setattr(r, "last_output_at", OLD))
        assert run_worker_cli("worker", "recover", rec.worker_id, "--repo-root", str(repo)) == 1
        assert "not stalled" in capsys.readouterr().err
        after = wait_for_worker(repo, rec.worker_id, timeout=30)
        assert after.state == "idle" and after.recoveries == 1 and ws.FLAG_STALLED not in after.flags
        assert [e.type for e in ws.events_since(repo, rec.worker_id)].count("resumed") == 1
        assert git(repo, "rev-parse", "HEAD") == head and (repo / "wip.txt").read_text() == "uncommitted\n"
    finally:
        if ws.load_record(repo, rec.worker_id).state != "terminated":
            ops.terminate(repo, rec.worker_id)


@pytest.mark.slow
def test_recover_ends_a_live_harness_whose_wrapper_died(tmp_path: Path, capsys) -> None:
    repo, rec = _silent_worker(tmp_path)
    try:
        os.kill(rec.pid, signal.SIGKILL)   # the wrapper this test started; its harness lives on in the group
        os.waitpid(rec.pid, 0)
        ws.mutate(repo, rec, lambda r: setattr(r, "last_output_at", OLD))
        assert run_worker_cli("worker", "sync", "--repo-root", str(repo)) == 0
        capsys.readouterr()
        assert ws.FLAG_ORPHAN in ws.load_record(repo, rec.worker_id).flags
        assert run_worker_cli("worker", "recover", rec.worker_id, "--json", "--repo-root", str(repo)) == 0
        out = json.loads(capsys.readouterr().out)
        assert ws.FLAG_ORPHAN not in out["flags"] and out["pid"] != rec.pid
        with pytest.raises(ProcessLookupError):   # the old harness was ended before the flag went
            os.kill(rec.harness_pid, 0)
        assert wait_for_worker(repo, rec.worker_id, timeout=30).state == "idle"
    finally:
        if ws.load_record(repo, rec.worker_id).state != "terminated":
            ops.terminate(repo, rec.worker_id)


@pytest.mark.slow
def test_a_recovery_whose_resume_was_refused_is_finished_by_the_next_call(tmp_path: Path, capsys) -> None:
    repo, rec = _silent_worker(tmp_path)
    try:
        git(repo, "remote", "add", "origin", "https://127.0.0.1:1/unreachable.git")   # the lease push will fail
        git(repo, "update-ref", "refs/remotes/origin/dev", "dev")   # as a clone has them: the config reads dev
        git(repo, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/dev")
        ws.mutate(repo, rec, lambda r: setattr(r, "last_output_at", OLD))
        assert run_worker_cli("worker", "recover", rec.worker_id, "--repo-root", str(repo)) == 1
        assert "cannot reach origin" in capsys.readouterr().err
        ended = ws.load_record(repo, rec.worker_id)
        assert not wrapper_alive(rec, repo) and ended.recoveries == 1
        # Pending, not lost: listed (and so retried by grind-session's loop), then finished offline uncounted.
        assert run_worker_cli("worker", "list", "--repo-root", str(repo)) == 0
        assert f"recovery pending: {rec.worker_id} (M1.1) recovery 1/3" in capsys.readouterr().out
        assert run_worker_cli("worker", "recover", rec.worker_id, "--offline", "--repo-root", str(repo)) == 0
        capsys.readouterr()
        after = wait_for_worker(repo, rec.worker_id, timeout=30)
        assert after.state == "idle" and after.recoveries == 1
        assert slots.stalled_workers(repo) == []   # finished: neither stalled nor pending
    finally:
        if "origin" in git(repo, "remote").split():
            git(repo, "remote", "remove", "origin")   # terminate releases the lease without a remote to reach
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



# --- F5, F8, F16 ----------------------------------------------------------------

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

def test_a_dead_wrapper_frees_the_leaf(tmp_path: Path) -> None:
    repo, _ = make_worker_repo(tmp_path, max_workers=4)
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    ws.set_state(repo, rec, "running", pid=999999)
    again, created = ops.delegate(repo, "M1.1", "opus")
    assert created and again.worker_id != rec.worker_id
    assert ws.load_record(repo, rec.worker_id).state == "failed"
    wait_for_worker(repo, again.worker_id)



# --- F11 (a) / G2 ---------------------------------------------------------------

def _dead_pid() -> int:
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    return p.pid



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

def test_sync_and_delegate_reap_dead_wrappers_on_any_leaf(tmp_path: Path) -> None:
    repo, _ = make_worker_repo(tmp_path, max_workers=1)
    dead = ws.create_record(repo, "M1.2", "claude-code", "opus", repo)
    ws.set_state(repo, dead, "running", pid=_dead_pid())
    assert wrc.sync(repo, ack=True)
    delta = wrc.sync(repo)
    assert delta == [] and ws.load_record(repo, dead.worker_id).state == "failed"
    assert [e.type for e in ws.events_since(repo, dead.worker_id)][-1] == "error"
    # A second dead record, not yet swept, must not hold the single slot.
    dead2 = ws.create_record(repo, "M1.3", "claude-code", "opus", repo)
    ws.set_state(repo, dead2, "running", pid=_dead_pid())
    rec, created = ops.delegate(repo, "M1.1", "opus")
    assert created and ws.load_record(repo, dead2.worker_id).state == "failed"
    wait_for_worker(repo, rec.worker_id)



# --- B9 ---------------------------------------------------------------------------

# READY freshness is a content checkpoint, not an mtime window; a wrapper that dies does not free
# a leaf whose harness is alive, and `terminate` kills the recorded group; the launch payload
# travels in a 0600 file, never in argv; a pid is this worker's wrapper only with the repo root,
# worker id and token as whole arguments (and `PermissionError` is not "ours"); completion, resume
# and reclaim check the branch actually checked out; parsed output is `worker_suggestion`, not
# `system`.

@pytest.mark.slow
@pytest.mark.skipif(not hasattr(signal, "SIGKILL"), reason="POSIX signals")
def test_a_dead_wrapper_with_a_live_harness_keeps_the_leaf_and_terminate_kills_the_group(tmp_path: Path) -> None:
    repo, script = make_worker_repo(tmp_path)
    slow = tmp_path / "slow.json"
    slow.write_text(json.dumps({"lines": [{"type": "system", "subtype": "init", "session_id": "slow"}], "sleep": 30}))
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    wr.spawn(repo, rec, wa.Launch([sys.executable, str(script), str(slow)]))
    for _ in range(100):
        rec = ws.load_record(repo, rec.worker_id)
        if rec.provider_session_id and rec.harness_pid:
            break
        time.sleep(0.1)
    assert rec.pgid == rec.pid and rec.harness_pid and rec.harness_start and rec.wrapper_token
    assert wp.wrapper_alive(rec, repo) and wp.harness_alive(rec)
    os.kill(rec.pid, signal.SIGKILL)
    time.sleep(0.3)
    assert not wp.wrapper_alive(rec, repo) and wp.harness_alive(rec)
    assert ops._wrapper_gone(repo, ws.load_record(repo, rec.worker_id)) is False
    rec = ws.load_record(repo, rec.worker_id)
    assert rec.state == "running" and ws.FLAG_ORPHAN in rec.flags
    evs = ws.events_since(repo, rec.worker_id)
    assert "harness pid" in evs[-1].summary and "still alive" in evs[-1].summary
    assert ops._wrapper_gone(repo, rec) is False and len(ws.events_since(repo, rec.worker_id)) == len(evs)  # said once
    with pytest.raises(ws.WorkerError, match="still running"):
        ops.resume(repo, rec.worker_id)
    with pytest.raises(ws.WorkerError, match="running"):
        ops.handoff(repo, rec.worker_id)
    _r, created = ops.delegate(repo, "M1.1", "opus")
    assert not created                                              # the leaf is still owned
    pgid = rec.pgid
    ops.terminate(repo, rec.worker_id)
    assert ws.load_record(repo, rec.worker_id).state == "terminated"
    assert not wp._group_members(pgid)



def test_once_the_whole_group_is_gone_the_record_is_failed(tmp_path: Path) -> None:
    repo, _ = make_worker_repo(tmp_path)
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    ws.mutate(repo, rec, lambda r: (setattr(r, "state", "running"), setattr(r, "pid", 999999),
                                    setattr(r, "pgid", 999999), setattr(r, "harness_pid", 999998)))
    assert ops._wrapper_gone(repo, ws.load_record(repo, rec.worker_id)) is True
    assert ws.load_record(repo, rec.worker_id).state == "failed"



# --- B11 ----------------------------------------------------------------------------

def test_pid_verification_needs_repo_root_worker_id_and_token_as_whole_args(monkeypatch) -> None:
    me = os.getpid()
    monkeypatch.setattr(wp, "_cmdline", lambda pid: "python -m specy_road.worker_runner /other/repository w-0001 tok1 /p")
    assert not wp.pid_alive(me, "w-0001", repo_root=Path("/r"), token="tok1")
    assert not wp.pid_verified(me, "w-0001", repo_root=Path("/r"), token="tok1")
    monkeypatch.setattr(wp, "_cmdline", lambda pid: "python -m specy_road.worker_runner /r w-0001 tok2 /p")
    assert not wp.pid_alive(me, "w-0001", repo_root=Path("/r"), token="tok1")     # same repo, a later spawn's token
    assert not wp.pid_alive(me, "w-00011", repo_root=Path("/r"), token="tok2")    # a prefix is not the id
    monkeypatch.setattr(wp, "_cmdline", lambda pid: "python -m specy_road.worker_runner /r w-0001 tok1 /p")
    assert wp.pid_alive(me, "w-0001", repo_root=Path("/r"), token="tok1")
    assert wp.pid_verified(me, "w-0001", repo_root=Path("/r"), token="tok1")
    rec = ws.WorkerRecord("w-0001", "M1.1", "claude-code", "opus", "/r", "running", {"holder": "broker", "since": "t"},
                          0, 1, 0, "t", "t", pid=me, wrapper_token="tok9")
    assert not wp.wrapper_alive(rec, Path("/r"))                                 # the record's token rules



def test_a_pid_our_user_cannot_signal_is_not_our_wrapper(monkeypatch) -> None:
    def denied(pid, sig):
        raise PermissionError(pid)
    monkeypatch.setattr(wp.os, "kill", denied)
    monkeypatch.setattr(wp, "_cmdline", lambda pid: "some other user's process")
    assert not wp.pid_alive(4242, "w-0001")
    assert not wp.pid_verified(4242, "w-0001")
    monkeypatch.setattr(wp, "_cmdline", lambda pid: None)                       # ps cannot say either
    assert not wp.pid_alive(4242, "w-0001")
    monkeypatch.setattr(wp, "_cmdline", lambda pid: "python -m specy_road.worker_runner /r w-0001 tok /p")
    assert wp.pid_alive(4242, "w-0001", repo_root=Path("/r"), token="tok")      # only the command line can confirm it



# One test per finding: records survive a concurrent writer (the wrapper no longer writes a stale
# copy back), two delegates on one leaf launch once, terminate reaches the harness and its
# children, an op id names one operation, an older attempt's READY does not complete a new worker,
# and the harness does not inherit the wrapper's PYTHONPATH.

def test_a_wrapper_with_a_long_command_line_is_still_recognised(tmp_path: Path) -> None:
    """procps ``ps`` without a terminal cuts ``-o command=`` at 80 columns unless ``-ww`` (cloud pre-release run)."""
    from specy_road.orchestration.workers import worker_process as wp
    deep = tmp_path / ("d" * 120) / "r"
    p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)", "specy_road.worker_runner", str(deep), "w-0042", "{}"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            if "w-0042" in (wp._cmdline(p.pid) or ""):
                break
            time.sleep(0.1)
        assert wp.pid_alive(p.pid, "w-0042") and wp.pid_verified(p.pid, "w-0042")
    finally:
        p.kill()
        p.wait()



@pytest.mark.parametrize("module", [
    "specy_road.worker_runner",                          # launched before the move
    "specy_road.orchestration.workers.worker_runner",
])
def test_a_wrapper_launched_under_either_module_name_is_live(tmp_path: Path, module: str) -> None:
    """A wrapper an older specy-road started as ``-m specy_road.worker_runner`` is still live."""
    repo = tmp_path.resolve()
    argv = ["-P", "-m", module, str(repo), "w-0042", "tok42", str(repo / "payload.json")]
    p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)", *argv],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    rec = ws.WorkerRecord("w-0042", "M1.1", "claude-code", "opus", str(repo), "running",
                          {"holder": "broker", "since": "t"}, 0, 1, 0, "t", "t",
                          pid=p.pid, wrapper_token="tok42")
    try:
        deadline = time.monotonic() + 5
        while not wp.wrapper_verified(rec, repo) and time.monotonic() < deadline:   # ps may lag
            time.sleep(0.1)
        assert wp.wrapper_verified(rec, repo) and wp.wrapper_alive(rec, repo)
    finally:
        p.kill()
        p.wait()



def test_pid_alive_ignores_a_reused_pid(monkeypatch) -> None:
    me = os.getpid()                       # alive, but not a wrapper
    assert not wr.pid_alive(me)
    monkeypatch.setattr(wp, "_cmdline", lambda pid: "python -m specy_road.worker_runner /r w-0001")
    assert wr.pid_alive(me)
    monkeypatch.setattr(wp, "_cmdline", lambda pid: None)   # ps unavailable: fall back to liveness
    assert wr.pid_alive(me)
