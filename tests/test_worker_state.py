"""Worker records, event log, leases and the op outbox under work/.workers/ (slice 7a)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.review_repo_helpers import git, make_review_repo

from specy_road import worker_state as ws


def _repo(tmp_path: Path) -> Path:
    return make_review_repo(tmp_path)


def test_create_load_list_and_ids(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    a = ws.create_record(repo, "M1.1", "claude-code", "opus", repo, branch="feature/rm-thing", contract_hash="abc")
    b = ws.create_record(repo, "M1.2", "codex", "sol", repo)
    assert (a.worker_id, b.worker_id) == ("w-0001", "w-0002")
    assert a.state == "starting" and a.lease["holder"] == "broker" and a.attempt == 1
    assert ws.load_record(repo, "w-0001").to_dict() == a.to_dict()
    assert [r.worker_id for r in ws.list_records(repo)] == ["w-0001", "w-0002"]
    assert ws.active_for_node(repo, "M1.1").worker_id == "w-0001"
    # The first event is the delegation itself.
    evs = ws.events_since(repo, "w-0001")
    assert [e.type for e in evs] == ["started"] and "claude-code/opus" in evs[0].summary
    assert a.last_event_seq == 1


def test_attempts_count_per_node_and_terminal_states_free_the_node(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    a = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    ws.set_state(repo, a, "failed", pid=None)
    assert ws.active_for_node(repo, "M1.1") is None
    b = ws.create_record(repo, "M1.1", "codex", "sol", repo)
    assert b.attempt == 2 and ws.active_for_node(repo, "M1.1").worker_id == b.worker_id
    assert [r.worker_id for r in ws.list_records(repo, active_only=True)] == [b.worker_id]


def test_records_live_in_the_main_worktree(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    git(repo, "checkout", "-q", "dev")
    wt = tmp_path / "wt"
    git(repo, "worktree", "add", "-q", str(wt), "feature/rm-thing")
    rec = ws.create_record(wt, "M1.1", "cursor", "composer", wt)
    assert ws.record_path(repo, rec.worker_id).is_file()
    assert ws.load_record(repo, rec.worker_id).worktree == str(wt.resolve())


def test_events_are_sequenced_validated_and_read_back_after_a_fresh_load(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    ws.append_event(repo, rec, "output", source="worker", summary="x" * 900, detail={"k": 1})
    ws.append_event(repo, rec, "completion", source="worker", summary="READY written", op_id="op-1")
    again = ws.load_record(repo, rec.worker_id)
    assert again.last_event_seq == 3
    evs = ws.events_since(repo, rec.worker_id, 1)
    assert [e.seq for e in evs] == [2, 3] and len(evs[0].summary) == 500 and evs[1].op_id == "op-1"
    assert ws.events_since(repo, rec.worker_id, 3) == []
    with pytest.raises(ws.WorkerError, match="type"):
        ws.append_event(repo, rec, "not-a-type", source="worker", summary="x")
    # A corrupt line is skipped, not fatal.
    with ws.events_path(repo, rec.worker_id).open("a") as f:
        f.write("{not json\n")
    assert len(ws.events_since(repo, rec.worker_id)) == 3


def test_lease_blocks_the_broker_until_reclaimed(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    ws.require_writer(rec)
    ws.set_lease(repo, rec, "human")
    with pytest.raises(ws.LeaseError, match="WORKER_LEASED_BY_HUMAN"):
        ws.require_writer(rec)
    ws.require_writer(rec, "human")
    ws.set_lease(repo, rec, "native")
    with pytest.raises(ws.LeaseError, match="WORKER_NATIVE_OWNED"):
        ws.require_writer(rec)
    with pytest.raises(ws.WorkerError, match="lease holder"):
        ws.set_lease(repo, rec, "me")
    ws.set_lease(repo, rec, "broker")
    assert ws.load_record(repo, rec.worker_id).lease["holder"] == "broker"


def test_intervention_bumps_the_epoch_and_checkpoint_records_head(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    rec = ws.create_record(repo, "M1.1", "codex", "sol", repo)
    cp = ws.take_checkpoint(repo, rec, native_turn="turn-7")
    assert cp["git_head"] == git(repo, "rev-parse", "HEAD") and cp["native_turn"] == "turn-7"
    ev = ws.record_intervention(repo, rec, "use the existing helper", source="hook", detail={"prompt": "..."})
    assert ev.authority == "human_authoritative" and ev.epoch == 1 and ev.type == "intervention"
    assert ws.load_record(repo, rec.worker_id).instruction_epoch == 1
    ws.add_flag(repo, rec, ws.FLAG_EXTERNAL)
    ws.add_flag(repo, rec, ws.FLAG_EXTERNAL)
    assert ws.load_record(repo, rec.worker_id).flags == [ws.FLAG_EXTERNAL]
    ws.clear_flag(repo, rec, ws.FLAG_EXTERNAL)
    assert ws.load_record(repo, rec.worker_id).flags == []


def test_invalid_records_are_refused_on_save_and_load(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    with pytest.raises(ws.WorkerError, match="harness"):
        ws.create_record(repo, "M1.1", "copilot", "x", repo)
    rec = ws.create_record(repo, "M1.1", "generic", "x", repo)
    rec.state = "dancing"
    with pytest.raises(ws.WorkerError, match="state"):
        ws.save_record(repo, rec)
    ws.record_path(repo, "w-0001").write_text("worker_id: w-0001\n")
    with pytest.raises(ws.WorkerError, match="required"):
        ws.load_record(repo, "w-0001")
    assert ws.list_records(repo) == []           # skipped, not fatal
    with pytest.raises(ws.WorkerError, match="no record"):
        ws.load_record(repo, "w-9999")
    with pytest.raises(ws.WorkerError, match="w-NNNN"):
        ws.record_path(repo, "../x")


def test_op_outbox_answers_a_retry_from_the_first_result(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    assert ws.begin_op(repo, "op-1", "delegate") is None
    with pytest.raises(ws.WorkerError, match="still pending"):
        ws.begin_op(repo, "op-1", "delegate")
    ws.complete_op(repo, "op-1", {"worker_id": "w-0001"})
    old = ws.begin_op(repo, "op-1", "delegate")
    assert old["state"] == "applied" and old["result"] == {"worker_id": "w-0001"}
    ws.begin_op(repo, "op-2", "message", "w-0001")
    ws.complete_op(repo, "op-2", {"error": "boom"}, ok=False)
    assert ws.begin_op(repo, "op-2", "message")["state"] == "failed"
    with pytest.raises(ws.WorkerError, match="op id"):
        ws.begin_op(repo, "bad/op", "x")


def test_schemas_ship_in_the_package(tmp_path: Path) -> None:
    pkg = Path(ws.__file__).resolve().parent / "schemas"
    for name in ("worker-record.schema.json", "worker-event.schema.json"):
        assert json.loads((pkg / name).read_text())["title"].startswith("specy-road")
