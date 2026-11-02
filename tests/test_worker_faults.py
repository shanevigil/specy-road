"""A harness killed by a signal under a live wrapper (sandbox runbook §5 step 9b (ii)).

The wrapper records an ``error`` event and marks the worker ``failed``; a
failed worker is closed, so ``resume`` refuses it. The exit code is ``-9``
where the adapter's ``sh -c`` execs the harness (bash, macOS) and ``137``
where it forks it (dash, the Debian/Ubuntu ``/bin/sh``).
"""

from __future__ import annotations

import signal
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from tests.review_repo_helpers import make_review_repo
from tests.test_worker_cli import _repo, worker_roster

from specy_road import worker_adapters as wa
from specy_road import worker_ops as ops
from specy_road import worker_runner as wr
from specy_road import worker_state as ws

KILLED = '''
import json, os, signal
print(json.dumps({"type": "system", "subtype": "init", "session_id": "s-killed", "model": "fake"}), flush=True)
os.kill(os.getpid(), signal.SIGKILL)
'''


@pytest.mark.skipif(not hasattr(signal, "SIGKILL"), reason="POSIX signals")
def test_a_killed_harness_leaves_the_worker_failed(tmp_path: Path) -> None:
    repo, _ = _repo(tmp_path)
    script = tmp_path / "killed.py"
    script.write_text(KILLED)
    prompt = tmp_path / "prompt.md"
    prompt.write_text("go")
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo, branch="feature/rm-thing")
    launch = wa.adapter_for("claude-code").launch(prompt, repo, "opus", f"{sys.executable} {script} {{prompt}}")
    code = wr.run(repo, rec.worker_id, launch)
    assert code in (-signal.SIGKILL, 128 + signal.SIGKILL)
    after = ws.load_record(repo, rec.worker_id)
    assert after.state == "failed" and after.pid is None and after.provider_session_id == "s-killed"
    err = [e for e in ws.events_since(repo, rec.worker_id) if e.type == "error"]
    assert len(err) == 1 and err[0].source == "worker" and err[0].detail["exit"] == code
    # The launch was timed before the kill: launched, then the one line it printed, then the error.
    types = [e.type for e in ws.events_since(repo, rec.worker_id)]
    assert types.index("launched") < types.index("first_output") < types.index("error")
    with pytest.raises(ws.WorkerError, match="is failed; delegate again instead"):
        ops.resume(repo, rec.worker_id)


PACED_LINES = '''
import sys, time
for i, pause in enumerate(float(x) for x in sys.argv[1:]):
    time.sleep(pause)
    print(f"line {i}", flush=True)
'''


def _paced(tmp_path: Path, *pauses: float) -> wa.Launch:
    """A harness that prints one line after each pause (seconds, real time)."""
    script = tmp_path / "paced.py"
    script.write_text(PACED_LINES)
    return wa.Launch([sys.executable, str(script), *(str(x) for x in pauses)])


def _since_launch(repo: Path, wid: str) -> float:
    """Seconds from the latest turn's ``launched`` event to the persisted ``last_output_at``."""
    launched = [e for e in ws.events_since(repo, wid) if e.type == "launched"][-1]
    out = ws.load_record(repo, wid).last_output_at
    return (datetime.fromisoformat(out) - datetime.fromisoformat(launched.at)).total_seconds()


def _stall_repo(tmp_path: Path, seconds: int) -> Path:
    """A review repo whose committed policy (read from the integration branch) sets ``stall_after_seconds``."""
    roster = worker_roster("harness {prompt}").replace(
        "policy: {max_workers: 2}", f"policy: {{max_workers: 2, stall_after_seconds: {seconds}}}")
    return make_review_repo(tmp_path, orchestration=roster)


def test_last_output_at_is_written_at_most_every_five_seconds(tmp_path: Path) -> None:
    repo, _ = _repo(tmp_path)
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo, branch="feature/rm-thing")
    launch = _paced(tmp_path, 0, 2.2)   # two lines about 2.2 s apart
    # Clock readings 0 and 1: the second line is inside the window, so the first line's time stays.
    wr.run(repo, rec.worker_id, launch, clock=iter([0.0, 1.0]).__next__)
    assert _since_launch(repo, rec.worker_id) <= 1
    # Readings 0 and 6: the second line is past the window, and its time is written.
    wr.run(repo, rec.worker_id, launch, clock=iter([0.0, 6.0]).__next__)
    assert _since_launch(repo, rec.worker_id) >= 2


def test_a_new_turn_resets_last_output_at_and_the_stalled_mark(tmp_path: Path) -> None:
    repo, _ = _repo(tmp_path)
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo, branch="feature/rm-thing")
    ws.mutate(repo, rec, lambda r: (setattr(r, "last_output_at", "2026-01-01T00:00:00+00:00"), r.flags.append(ws.FLAG_STALLED)))
    wr.run(repo, rec.worker_id, _paced(tmp_path))   # prints nothing: only the launch sets the time
    assert 0 <= _since_launch(repo, rec.worker_id) <= 1
    assert ws.FLAG_STALLED not in ws.load_record(repo, rec.worker_id).flags


def _stalled(repo: Path, wid: str) -> list[ws.WorkerEvent]:
    return [e for e in ws.events_since(repo, wid) if e.type == "stalled"]


def test_a_silent_running_worker_is_flagged_once_per_silence(tmp_path: Path) -> None:
    repo, _ = _repo(tmp_path)
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    t0 = datetime.fromisoformat("2026-11-01T00:00:00+00:00")
    ws.mutate(repo, rec, lambda r: (setattr(r, "state", "running"), setattr(r, "last_output_at", t0.isoformat())))
    ws.append_event(repo, rec, "output", source="worker", authority="worker_suggestion", summary="Bash: pytest -x")
    assert ops.sweep_stalled(repo, now=t0 + timedelta(seconds=599)) == [] and not _stalled(repo, rec.worker_id)
    assert [r.worker_id for r in ops.sweep_stalled(repo, now=t0 + timedelta(seconds=600))] == [rec.worker_id]
    [ev] = _stalled(repo, rec.worker_id)
    assert ev.detail["silent_seconds"] == 600 and "600s" in ev.summary and "Bash: pytest -x" in ev.summary
    assert ws.FLAG_STALLED in ws.load_record(repo, rec.worker_id).flags
    assert ops.sweep_stalled(repo, now=t0 + timedelta(seconds=900)) == []   # the same silence: no second event
    assert len(_stalled(repo, rec.worker_id)) == 1
    # Only a running worker is stalled: the flag goes when the turn ends.
    ws.set_state(repo, rec, "idle")
    ops.sweep_stalled(repo, now=t0 + timedelta(seconds=900))
    assert ws.FLAG_STALLED not in ws.load_record(repo, rec.worker_id).flags


def test_output_clears_a_stall_shorter_than_the_write_window(tmp_path: Path) -> None:
    """stall_after_seconds 1: a sweep flags each 3 s silence, and the line after it clears the flag,
    although that line falls inside the five-second last_output_at window."""
    import threading
    import time

    repo = _stall_repo(tmp_path, 1)
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo, branch="feature/rm-thing")
    raw = wr.log_path(repo, rec.worker_id)
    newly_flagged: list[bool] = []
    errors: list[BaseException] = []

    def sweeper() -> None:
        try:
            for n in (1, 2):   # 1.5 s into the silence after line n
                deadline = time.monotonic() + 10
                while (raw.read_text().count("line ") if raw.is_file() else 0) < n:
                    assert time.monotonic() < deadline, f"line {n} never reached the log"
                    time.sleep(0.05)
                time.sleep(1.5)
                newly_flagged.append(bool(ops.sweep_stalled(repo)))
        except BaseException as e:  # noqa: BLE001 — reported by the test thread
            errors.append(e)

    t = threading.Thread(target=sweeper)
    t.start()
    wr.run(repo, rec.worker_id, _paced(tmp_path, 0, 3, 3))
    t.join()
    assert not errors, errors
    # The second sweep flags afresh only because line 1 cleared the first flag.
    assert newly_flagged == [True, True] and len(_stalled(repo, rec.worker_id)) == 2
    # Line 1 also wrote its time: the second silence is measured from it, not from line 0.
    assert _stalled(repo, rec.worker_id)[1].detail["silent_seconds"] < 3
    # Line 2 cleared the second flag (the turn's end does not touch flags).
    assert ws.FLAG_STALLED not in ws.load_record(repo, rec.worker_id).flags


def test_list_and_sync_flag_a_live_silent_worker(tmp_path: Path, capsys) -> None:
    import json
    import time

    from tests.test_worker_cli import run_worker_cli

    repo, script = _repo(tmp_path)
    spec = tmp_path / "silent.json"
    spec.write_text(json.dumps({"lines": [{"type": "system", "subtype": "init", "session_id": "quiet"}], "sleep": 30}))
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    wr.spawn(repo, rec, wa.Launch([sys.executable, str(script), str(spec)]))
    try:
        for _ in range(50):
            if ws.load_record(repo, rec.worker_id).provider_session_id:
                break
            time.sleep(0.1)
        old = "2026-01-01T00:00:00+00:00"   # long past policy.stall_after_seconds (default 600)
        ws.mutate(repo, rec, lambda r: setattr(r, "last_output_at", old))
        assert run_worker_cli("worker", "list", "--repo-root", str(repo)) == 0
        assert "[stalled]" in capsys.readouterr().out and len(_stalled(repo, rec.worker_id)) == 1
        ws.clear_flag(repo, rec, ws.FLAG_STALLED)   # as the wrapper's next write would, still silent since `old`
        assert run_worker_cli("worker", "sync", "--json", "--repo-root", str(repo)) == 0
        [w] = json.loads(capsys.readouterr().out)["workers"]
        assert "stalled" in w["flags"] and [e["type"] for e in w["events"]].count("stalled") == 2
    finally:
        ops.terminate(repo, rec.worker_id)


def test_policy_stall_after_seconds_overrides_the_default(tmp_path: Path) -> None:
    repo = _stall_repo(tmp_path, 60)
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    t0 = datetime.fromisoformat("2026-11-01T00:00:00+00:00")
    ws.mutate(repo, rec, lambda r: (setattr(r, "state", "running"), setattr(r, "last_output_at", t0.isoformat())))
    assert ops.sweep_stalled(repo, now=t0 + timedelta(seconds=59)) == []
    assert len(ops.sweep_stalled(repo, now=t0 + timedelta(seconds=60))) == 1   # well under the default 600
    assert "stall_after_seconds 60" in _stalled(repo, rec.worker_id)[0].summary
