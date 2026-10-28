"""Regressions from the sixth independent review, runner side (2026-10-27): B3, B9, B10, B11, B12, F9.

READY freshness is a content checkpoint, not an mtime window; a wrapper that
dies does not free a leaf whose harness is alive, and ``terminate`` kills the
recorded group; the launch payload travels in a 0600 file, never in argv; a
pid is this worker's wrapper only with the repo root, worker id and token as
whole arguments (and ``PermissionError`` is not "ours"); completion, resume
and reclaim check the branch actually checked out; parsed output is
``worker_suggestion``, not ``system``.
"""

from __future__ import annotations

import json
import os
import signal
import sys
import time
from pathlib import Path

import pytest

from tests.review_repo_helpers import git
from tests.test_worker_cli import _repo, _wait

from specy_road import worker_adapters as wa
from specy_road import worker_ops as ops
from specy_road import worker_process as wp
from specy_road import worker_runner as wr
from specy_road import worker_state as ws
from specy_road.review_files import reviews_root

OK = [{"type": "result", "subtype": "success", "result": "ok", "session_id": "n"}]


def _ready_text(repo: Path, commit: str, agent: str = "x", branch: str = "feature/rm-thing") -> str:
    return (f"---\nnode_id: M1.1\nagent: {agent}\nbranch: {branch}\ncommit: {commit}\nbase: {commit}\n"
            "changed_paths: []\nverify: []\n---\n")


def _launch(tmp_path: Path, script: Path, repo: Path, name: str, **spec):
    p = tmp_path / f"{name}.json"
    p.write_text(json.dumps({"lines": OK, **spec}))
    return wa.adapter_for("claude-code").launch(p, repo, "opus", f"{sys.executable} {script} {{prompt}}")


# --- B3 ---------------------------------------------------------------------------

def test_a_ready_written_just_before_the_turn_does_not_complete_it_and_a_rewritten_one_does(tmp_path: Path) -> None:
    repo, script = _repo(tmp_path)
    d = reviews_root(repo) / "M1.1"
    d.mkdir(parents=True)
    head = git(repo, "rev-parse", "HEAD")
    ready = d / "READY-x.md"
    ready.write_text(_ready_text(repo, head))           # 0 s before the turn: the mtime window accepted this
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo, branch="feature/rm-thing")
    assert wr.run(repo, rec.worker_id, _launch(tmp_path, script, repo, "quiet")) == 0
    assert ws.load_record(repo, rec.worker_id).state == "idle"
    # The same path rewritten with new content during the turn is a new READY, whatever the clock says.
    old = time.time() - 3600
    os.utime(ready, (old, old))
    rewrite = {"path": str(ready), "text": _ready_text(repo, head, agent="y")}
    wr.run(repo, rec.worker_id, _launch(tmp_path, script, repo, "writes", write=rewrite), resumed=True)
    assert ws.load_record(repo, rec.worker_id).state == "completed"
    assert wp.ready_fingerprints(repo, "M1.1") == [f"READY-x.md:{__import__('hashlib').sha256(ready.read_bytes()).hexdigest()}"]


def test_the_checkpoint_is_by_content_not_mtime(tmp_path: Path) -> None:
    repo, _ = _repo(tmp_path)
    d = reviews_root(repo) / "M1.1"
    d.mkdir(parents=True)
    head = git(repo, "rev-parse", "HEAD")
    (d / "READY-a.md").write_text(_ready_text(repo, head))
    before = wp.ready_fingerprints(repo, "M1.1")
    future = time.time() + 600
    os.utime(d / "READY-a.md", (future, future))
    assert wp.new_ready(repo, "M1.1", before) is None               # touched, not changed
    (d / "READY-b.md").write_text(_ready_text(repo, head, agent="b"))
    assert wp.new_ready(repo, "M1.1", before).path.name == "READY-b.md"   # new, though its mtime is older than a's


# --- B9 ---------------------------------------------------------------------------

@pytest.mark.skipif(not hasattr(signal, "SIGKILL"), reason="POSIX signals")
def test_a_dead_wrapper_with_a_live_harness_keeps_the_leaf_and_terminate_kills_the_group(tmp_path: Path) -> None:
    repo, script = _repo(tmp_path)
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
    repo, _ = _repo(tmp_path)
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    ws.mutate(repo, rec, lambda r: (setattr(r, "state", "running"), setattr(r, "pid", 999999),
                                    setattr(r, "pgid", 999999), setattr(r, "harness_pid", 999998)))
    assert ops._wrapper_gone(repo, ws.load_record(repo, rec.worker_id)) is True
    assert ws.load_record(repo, rec.worker_id).state == "failed"


# --- B10 ----------------------------------------------------------------------------

def test_a_huge_stdin_prompt_travels_in_a_0600_file_not_argv(tmp_path: Path) -> None:
    repo, _ = _repo(tmp_path)
    probe = tmp_path / "probe.py"
    probe.write_text("import json, sys\nn = len(sys.stdin.read())\n"
                     "print(json.dumps({'type': 'system', 'subtype': 'init', 'session_id': str(n)}), flush=True)\n")
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    seen = {}
    real = wr.subprocess.Popen

    def spy(argv, **kw):
        if "specy_road.worker_runner" in argv:       # the lock's git calls go through Popen too
            seen["argv"] = argv
            seen["mode"] = oct(Path(argv[-1]).stat().st_mode & 0o777)
        return real(argv, **kw)
    wr.subprocess.Popen = spy
    try:
        wr.spawn(repo, rec, wa.Launch([sys.executable, str(probe)], stdin="x" * 2_000_000))   # E2BIG before
    finally:
        wr.subprocess.Popen = real
    assert seen["mode"] == "0o600" and sum(len(a) for a in seen["argv"]) < 4096
    assert seen["argv"][3:6] == [str(repo.resolve()), rec.worker_id, ws.load_record(repo, rec.worker_id).wrapper_token]
    final = _wait(repo, rec.worker_id)
    assert final.provider_session_id == "2000000"
    assert not list((repo / "work" / ".workers").glob("*.launch-*.json"))   # read once and deleted


def test_a_prompt_in_argv_is_refused_above_the_limit_with_a_failed_record(tmp_path: Path) -> None:
    repo, _ = _repo(tmp_path)
    rec = ws.create_record(repo, "M1.1", "cursor", "composer", repo)
    with pytest.raises(ws.WorkerError, match=r"KiB of arguments \(limit 100 KiB\)"):
        wr.spawn(repo, rec, wa.Launch(["agent", "-p", "y" * (wp.ARGV_LIMIT + 1)]))
    rec = ws.load_record(repo, rec.worker_id)
    assert rec.state == "failed" and rec.pid is None
    assert "shorten the brief" in ws.events_since(repo, rec.worker_id)[-1].summary


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


# --- B12 ----------------------------------------------------------------------------

def test_completion_resume_and_reclaim_check_the_branch_actually_checked_out(tmp_path: Path) -> None:
    repo, script = _repo(tmp_path)
    d = reviews_root(repo) / "M1.1"
    d.mkdir(parents=True)
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo, branch="feature/rm-thing")
    git(repo, "checkout", "-q", "dev")
    head = git(repo, "rev-parse", "HEAD")
    write = {"path": str(d / "READY-x.md"), "text": _ready_text(repo, head)}   # declares the branch, at dev's HEAD
    assert wr.run(repo, rec.worker_id, _launch(tmp_path, script, repo, "w", write=write)) == 0
    rec = ws.load_record(repo, rec.worker_id)
    assert rec.state == "idle"
    why = [e for e in ws.events_since(repo, rec.worker_id) if "READY-x.md ignored" in e.summary]
    assert len(why) == 1 and "has dev checked out, not the worker's branch feature/rm-thing" in why[0].summary
    with pytest.raises(ws.WorkerError, match="has dev checked out"):
        ops.resume(repo, rec.worker_id)
    git(repo, "checkout", "-q", "feature/rm-thing")
    ops.handoff(repo, rec.worker_id)
    git(repo, "checkout", "-q", "dev")
    with pytest.raises(ws.WorkerError, match="has dev checked out"):
        ops.reclaim(repo, rec.worker_id)
    assert ws.load_record(repo, rec.worker_id).lease["holder"] == "human"
    git(repo, "checkout", "-q", "feature/rm-thing")
    ops.reclaim(repo, rec.worker_id)
    assert ws.load_record(repo, rec.worker_id).lease["holder"] == "broker"


def test_reconcile_flags_a_tree_off_the_workers_branch(tmp_path: Path) -> None:
    repo, _ = _repo(tmp_path)
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo, branch="feature/rm-thing")
    ws.set_state(repo, rec, "idle")
    git(repo, "checkout", "-q", "dev")
    _r, delta = ops.reconcile(repo, rec.worker_id)
    assert delta["needs_reconcile"] and "has dev checked out" in delta["branch_mismatch"]


# --- F9 ---------------------------------------------------------------------------

def test_parsed_output_is_worker_suggestion_and_lifecycle_stays_system(tmp_path: Path) -> None:
    repo, script = _repo(tmp_path)
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    lines = [{"type": "system", "subtype": "init", "session_id": "n"},
             {"type": "assistant", "message": {"content": [{"type": "text", "text": "hello"}]}},
             {"type": "result", "subtype": "success", "result": "ok"}]
    spec = tmp_path / "f9.json"
    spec.write_text(json.dumps({"lines": lines}))
    wr.run(repo, rec.worker_id, wa.adapter_for("claude-code").launch(spec, repo, "opus", f"{sys.executable} {script} {{prompt}}"))
    got = {(e.type, e.source): e.authority for e in ws.events_since(repo, rec.worker_id)}
    assert got[("started", "broker")] == "system" and got[("completion", "worker")] == "system"
    assert got[("started", "worker")] == got[("output", "worker")] == got[("turn_completed", "worker")] == "worker_suggestion"
