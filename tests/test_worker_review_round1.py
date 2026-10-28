"""Regressions from the first independent review of the worker layer (2026-10-27).

One test per finding: records survive a concurrent writer (the wrapper no
longer writes a stale copy back), two delegates on one leaf launch once,
terminate reaches the harness and its children, an op id names one
operation, an older attempt's READY does not complete a new worker, and the
harness does not inherit the wrapper's PYTHONPATH.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from tests.test_worker_cli import _cli, _repo, _wait

from specy_road import worker_adapters as wa
from specy_road import worker_ops as ops
from specy_road import worker_process as wp
from specy_road import worker_runner as wr
from specy_road import worker_state as ws
from specy_road.review_files import reviews_root


def test_a_flag_set_while_the_wrapper_streams_survives(tmp_path: Path) -> None:
    repo, _script = _repo(tmp_path)
    spec = tmp_path / "slow.json"
    spec.write_text(json.dumps({"lines": [{"type": "system", "subtype": "init", "session_id": "slow"},
                                          {"type": "assistant", "message": {"content": [{"type": "text", "text": "a"}]}},
                                          {"type": "result", "subtype": "success", "result": "ok"}], "sleep": 2}))
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    launch = wa.adapter_for("claude-code").launch(spec, repo, "opus", f"{sys.executable} {_script} {{prompt}}")
    wr.spawn(repo, rec, launch)
    time.sleep(0.8)
    ws.add_flag(repo, rec, ws.FLAG_RECONCILE)           # another process writes while it runs
    ws.append_event(repo, rec, "reconcile", source="orchestrator", summary="mid-run")
    _wait(repo, rec.worker_id)
    final = ws.load_record(repo, rec.worker_id)
    assert ws.FLAG_RECONCILE in final.flags
    seqs = [e.seq for e in ws.events_since(repo, rec.worker_id)]
    assert seqs == sorted(set(seqs)) and final.last_event_seq == seqs[-1]


def test_concurrent_delegates_on_one_leaf_launch_once(tmp_path: Path) -> None:
    repo, _ = _repo(tmp_path, max_workers=4)
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
    _wait(repo, "w-0001")


def test_terminate_reaches_the_harness_and_its_children(tmp_path: Path) -> None:
    repo, _ = _repo(tmp_path)
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
        time.sleep(0.1)
    assert marker.is_file()
    ops.terminate(repo, rec.worker_id)
    time.sleep(0.5)
    size = marker.stat().st_size
    time.sleep(0.5)
    assert marker.stat().st_size == size, "the harness's child kept writing after terminate"
    assert ws.load_record(repo, rec.worker_id).state == "terminated"


def test_terminate_refuses_a_handed_off_worker(tmp_path: Path) -> None:
    repo, _ = _repo(tmp_path)
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    ws.set_lease(repo, rec, "human")
    with pytest.raises(ws.WorkerError, match="reclaim"):
        ops.terminate(repo, rec.worker_id)


def test_an_op_id_names_one_operation(tmp_path: Path) -> None:
    repo, _ = _repo(tmp_path)
    assert ws.begin_op(repo, "X1", "reconcile", "w-0001") is None
    ws.complete_op(repo, "X1", {"ok": True})
    assert ws.begin_op(repo, "X1", "reconcile", "w-0001")["result"] == {"ok": True}
    with pytest.raises(ws.WorkerError, match="names one operation"):
        ws.begin_op(repo, "X1", "terminate", "w-0001")
    with pytest.raises(ws.WorkerError, match="names one operation"):
        ws.begin_op(repo, "X1", "reconcile", "w-0002")


def test_an_older_attempts_ready_does_not_complete_a_new_worker(tmp_path: Path) -> None:
    repo, script = _repo(tmp_path)
    d = reviews_root(repo) / "M1.1"
    d.mkdir(parents=True)
    from tests.review_repo_helpers import git

    head = git(repo, "rev-parse", "HEAD")
    ready = d / "READY-old.md"
    ready.write_text(f"---\nnode_id: M1.1\nagent: old\nbranch: feature/rm-thing\ncommit: {head}\nbase: {head}\n"
                     "changed_paths: []\nverify: []\n---\n")
    now = time.time() + 60   # even a future mtime is not freshness: the checkpoint is by content, not clock
    os.utime(ready, (now, now))
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    lines = [{"type": "result", "subtype": "success", "result": "ok", "session_id": "n"}]
    spec = tmp_path / "ok.json"
    spec.write_text(json.dumps({"lines": lines}))
    assert wr.run(repo, rec.worker_id, wa.adapter_for("claude-code").launch(spec, repo, "opus", f"{sys.executable} {script} {{prompt}}")) == 0
    assert ws.load_record(repo, rec.worker_id).state == "idle"      # not completed on an older attempt's READY
    rec2 = ws.create_record(repo, "M1.2", "claude-code", "opus", repo)
    rec2 = ws.mutate(repo, rec2, lambda r: setattr(r, "node_id", "M1.1"))
    spec2 = tmp_path / "writes.json"       # this worker's harness writes its own READY during the turn
    spec2.write_text(json.dumps({"lines": lines, "write": {"path": str(d / "READY-new.md"),
                                                           "text": ready.read_text().replace("agent: old", "agent: new")}}))
    wr.run(repo, rec2.worker_id, wa.adapter_for("claude-code").launch(spec2, repo, "opus", f"{sys.executable} {script} {{prompt}}"))
    assert ws.load_record(repo, rec2.worker_id).state == "completed"


def test_the_harness_does_not_inherit_the_wrappers_pythonpath(tmp_path: Path, monkeypatch) -> None:
    repo, _ = _repo(tmp_path)
    probe = tmp_path / "probe.py"
    probe.write_text("import json, os\nprint(json.dumps({'type': 'system', 'subtype': 'init', 'session_id': os.environ.get('PYTHONPATH', '(unset)')}), flush=True)\n")
    monkeypatch.setenv("PYTHONPATH", "/adopter/own/path")
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    wr.spawn(repo, rec, wa.Launch([sys.executable, str(probe)]))
    _wait(repo, rec.worker_id)
    assert ws.load_record(repo, rec.worker_id).provider_session_id == "/adopter/own/path"
    monkeypatch.delenv("PYTHONPATH")
    rec2 = ws.create_record(repo, "M1.2", "claude-code", "opus", repo)
    wr.spawn(repo, rec2, wa.Launch([sys.executable, str(probe)]))
    _wait(repo, rec2.worker_id)
    assert ws.load_record(repo, rec2.worker_id).provider_session_id == "(unset)"


def test_a_bad_output_line_does_not_kill_the_wrapper(tmp_path: Path) -> None:
    repo, _ = _repo(tmp_path)
    rec = ws.create_record(repo, "M1.1", "codex", "sol", repo)
    spec = tmp_path / "e.json"
    bad = tmp_path / "bad.py"
    bad.write_text("import json\nprint(json.dumps({'type': 'thread.started', 'thread_id': 't'}), flush=True)\n"
                   "print(json.dumps({'type': 'item.completed', 'item': {'type': 'agent_message', 'text': ''}}), flush=True)\n"
                   "print(json.dumps({'type': 'turn.completed'}), flush=True)\n")
    assert wr.run(repo, rec.worker_id, wa.Launch([sys.executable, str(bad)])) == 0
    final = ws.load_record(repo, rec.worker_id)
    assert final.state == "idle" and final.pid is None
    assert [e.type for e in ws.events_since(repo, rec.worker_id)][-1] == "completion"


def test_a_wrapper_with_a_long_command_line_is_still_recognised(tmp_path: Path) -> None:
    """procps ``ps`` without a terminal cuts ``-o command=`` at 80 columns unless ``-ww`` (cloud pre-release run)."""
    from specy_road import worker_process as wp
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


def test_pid_alive_ignores_a_reused_pid(monkeypatch) -> None:
    me = os.getpid()                       # alive, but not a wrapper
    assert not wr.pid_alive(me)
    monkeypatch.setattr(wp, "_cmdline", lambda pid: "python -m specy_road.worker_runner /r w-0001")
    assert wr.pid_alive(me)
    monkeypatch.setattr(wp, "_cmdline", lambda pid: None)   # ps unavailable: fall back to liveness
    assert wr.pid_alive(me)
