"""``worker message`` / ``resume`` reopen a failed or stalled worker whose native session id is known (M11.2).

A failed worker without a session id, and a terminated one, are still refused
with "delegate again instead"; the reopened turn takes a ``max_workers`` slot.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.review_repo_helpers import git
from tests.test_worker_cli import _repo, run_worker_cli, wait_for_worker

from specy_road import worker_ops as ops
from specy_road import worker_state as ws


def _failed(repo: Path, session: str | None = "sid-1", node: str = "M1.1") -> ws.WorkerRecord:
    rec = ws.create_record(repo, node, "claude-code", "opus", repo)
    if session:
        ws.mutate(repo, rec, lambda r: setattr(r, "provider_session_id", session))
    return ws.set_state(repo, rec, "failed", pid=None)


def test_message_resumes_a_failed_worker_with_a_session_id(tmp_path: Path, capsys) -> None:
    repo, _ = _repo(tmp_path)
    rec = _failed(repo)
    assert run_worker_cli("worker", "message", rec.worker_id, "--text", "finish the one file", "--repo-root", str(repo)) == 0
    assert "message sent; resumed" in capsys.readouterr().out
    after = wait_for_worker(repo, rec.worker_id)
    assert after.state == "idle" and after.provider_session_id == "sid-1"   # the same native session, not a new one
    types = [e.type for e in ws.events_since(repo, rec.worker_id)]
    assert types[types.index("message"):].count("resumed") == 1 and types[-1] == "completion"


def test_a_failed_worker_without_a_session_id_is_still_refused(tmp_path: Path, capsys) -> None:
    repo, _ = _repo(tmp_path)
    rec = _failed(repo, session=None)
    assert run_worker_cli("worker", "message", rec.worker_id, "--text", "x", "--repo-root", str(repo)) == 1
    assert "is failed, session none; delegate again instead" in capsys.readouterr().err
    with pytest.raises(ws.WorkerError, match="delegate again instead"):
        ops.resume(repo, rec.worker_id)
    assert ws.load_record(repo, rec.worker_id).state == "failed"


def test_an_unreadable_integration_ref_is_a_worker_error_for_a_failed_worker(tmp_path: Path) -> None:
    repo, _ = _repo(tmp_path)
    rec = _failed(repo)
    git(repo, "branch", "-D", "dev")   # the roster and policy are read from the integration branch
    for send in (lambda: ops.message(repo, rec.worker_id, "x"), lambda: ops.resume(repo, rec.worker_id)):
        with pytest.raises(ws.WorkerError, match="orchestration config"):
            send()
    assert ws.load_record(repo, rec.worker_id).state == "failed"


def test_a_stalled_worker_whose_process_ended_resumes(tmp_path: Path) -> None:
    repo, _ = _repo(tmp_path)
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    ws.mutate(repo, rec, lambda r: setattr(r, "provider_session_id", "sid-1"))
    ws.set_state(repo, rec, "running", pid=None)   # a harness stopped by hand: no wrapper, no harness left
    ws.add_flag(repo, rec, ws.FLAG_STALLED)
    ops.resume(repo, rec.worker_id)
    types = [e.type for e in ws.events_since(repo, rec.worker_id)]
    assert types.index("error") < types.index("message")   # recorded as failed first, then reopened
    assert wait_for_worker(repo, rec.worker_id).state == "idle"


def test_a_stalled_worker_that_is_still_alive_says_how_to_resume(tmp_path: Path, monkeypatch) -> None:
    repo, _ = _repo(tmp_path)
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    ws.mutate(repo, rec, lambda r: setattr(r, "provider_session_id", "sid-1"))
    ws.set_state(repo, rec, "running", pid=None)
    ws.add_flag(repo, rec, ws.FLAG_STALLED)
    monkeypatch.setattr(ops, "wrapper_gone", lambda *_a: False)
    monkeypatch.setattr(ops, "process_alive", lambda *_a: True)
    with pytest.raises(ws.WorkerError, match="stalled: once its harness exits, message resumes the session"):
        ops.message(repo, rec.worker_id, "x")


def test_the_reopened_turn_counts_against_max_workers(tmp_path: Path, capsys) -> None:
    repo, _ = _repo(tmp_path, max_workers=1)
    rec = _failed(repo)
    other = ws.create_record(repo, "M1.2", "generic", "x", repo)   # an idle worker on another leaf holds the one slot
    ws.set_state(repo, other, "idle", pid=None)
    assert run_worker_cli("worker", "message", rec.worker_id, "--text", "x", "--repo-root", str(repo)) == 1
    assert "1 workers active, policy max_workers is 1" in capsys.readouterr().err
    assert ws.load_record(repo, rec.worker_id).state == "failed"
    ws.set_state(repo, other, "terminated", pid=None)   # the slot frees: now it resumes
    ops.message(repo, rec.worker_id, "x")
    assert wait_for_worker(repo, rec.worker_id).state == "idle"


def test_a_leaf_already_held_by_another_worker_is_not_reopened(tmp_path: Path) -> None:
    repo, _ = _repo(tmp_path)
    rec = _failed(repo)
    newer = ws.create_record(repo, "M1.1", "generic", "x", repo)   # the leaf was delegated again
    ws.set_state(repo, newer, "idle", pid=None)
    with pytest.raises(ws.WorkerError, match=f"already has an active worker \\({newer.worker_id}\\); "
                                             f"{rec.worker_id} stays failed"):
        ops.message(repo, rec.worker_id, "x")
