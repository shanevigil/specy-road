"""Worker records, event log, leases and the op outbox under work/.workers/ (slice 7a)."""

from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path

import pytest

from tests.support.review import make_review_repo, git

from specy_road import git_workflow_config as gwc
from specy_road.orchestration.workers import worker_adapters as wa
from specy_road.orchestration.workers import worker_runner as wr
from specy_road.orchestration.workers import worker_state as ws
from specy_road.orchestration.workers.worker_cli_sync import wait_for_event
from specy_road.bundled_scripts import worker_cli
import os
from tests.support.harness import make_worker_repo, wait_for_worker
from specy_road.orchestration.workers import worker_lease as wl
from specy_road.orchestration.workers import worker_process as wp
import io
from datetime import datetime, timezone
from unittest import mock
import yaml
from tests.support.cli import run_worker_cli
from specy_road.orchestration.workers import worker_reconcile as wrc
from specy_road.orchestration.workers import worker_sessions as wsess
from specy_road.orchestration.workers import worker_lease as ww
from tests.support.extracted.folded_review_ops import idle_record
from specy_road.orchestration.workers import worker_ops as ops


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
    ws.append_event(repo, rec, "launched", source="system", summary="up", detail={"argv0": "claude", "harness": "claude-code", "resumed": False})
    ws.append_event(repo, rec, "first_output", source="system", summary="first line")
    assert [e.type for e in ws.events_since(repo, rec.worker_id, 3)] == ["launched", "first_output"]
    # A corrupt line is skipped, not fatal.
    with ws.events_path(repo, rec.worker_id).open("a") as f:
        f.write("{not json\n")
    assert len(ws.events_since(repo, rec.worker_id)) == 5


def test_every_event_replaces_the_mailbox_flag(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    assert ws.flag_stamp(repo) is None
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)   # its `started` event is the first
    first = ws.flag_stamp(repo)
    assert first is not None and (ws.workers_dir(repo) / "FLAG").read_text().startswith("w-0001 #1 ")
    ws.append_event(repo, rec, "output", source="worker", summary="x")
    assert ws.flag_stamp(repo) != first
    assert (ws.workers_dir(repo) / "FLAG").read_text().startswith("w-0001 #2 ")


@pytest.mark.slow
def test_wait_for_event_returns_on_the_next_event_or_times_out(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    since = ws.flag_stamp(repo)
    t0 = time.monotonic()
    assert wait_for_event(repo, 0.3, since) is False
    assert 0.3 <= time.monotonic() - t0 < 2
    writer = threading.Timer(0.4, lambda: ws.append_event(repo, rec, "output", source="worker", summary="late"))
    writer.start()
    t0 = time.monotonic()
    try:
        assert wait_for_event(repo, 10, since) is True
    finally:
        writer.join()
    assert time.monotonic() - t0 < 2   # within a poll of the write, not the 10 s timeout
    assert wait_for_event(repo, 10, None) is True   # the flag already changed since "no flag": no wait at all


def test_sync_wait_ctrl_c_exits_130_without_a_traceback(tmp_path: Path, capsys, monkeypatch) -> None:
    # Beside the wait itself: tests/flows/worker/test_worker_cli.py is at the file-line cap.
    repo = _repo(tmp_path)

    def interrupted(*_a):
        raise KeyboardInterrupt
    monkeypatch.setattr(
        "specy_road.orchestration.workers.worker_cli_sync.wait_for_sync", interrupted
    )
    with pytest.raises(SystemExit) as e:
        worker_cli.main(["worker", "sync", "--wait", "--repo-root", str(repo)])
    assert e.value.code == 130
    err = capsys.readouterr().err
    assert "interrupted; nothing acknowledged" in err and "Traceback" not in err


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


def test_checkpoint_records_head_and_a_flag_is_set_once(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    rec = ws.create_record(repo, "M1.1", "codex", "sol", repo)
    cp = ws.take_checkpoint(repo, rec, native_turn="turn-7")
    assert cp["git_head"] == git(repo, "rev-parse", "HEAD") and cp["native_turn"] == "turn-7"
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
    assert ws.begin_op(repo, "op-2", "message", "w-0001")["state"] == "failed"
    with pytest.raises(ws.WorkerError, match="names one operation"):   # the target is part of the op's identity
        ws.begin_op(repo, "op-2", "message")
    with pytest.raises(ws.WorkerError, match="op id"):
        ws.begin_op(repo, "bad/op", "x")


def test_schemas_ship_in_the_package(tmp_path: Path) -> None:
    pkg = Path(ws.__file__).resolve().parents[2] / "schemas"
    for name in ("worker-record.schema.json", "worker-event.schema.json"):
        assert json.loads((pkg / name).read_text())["title"].startswith("specy-road")


def _track(repo: Path, line: str) -> None:
    cfg = repo / "roadmap" / "git-workflow.yaml"
    cfg.write_text("version: 1\nintegration_branch: dev\nremote: origin\n" + line, encoding="utf-8")


@pytest.mark.parametrize(("line", "mode"), [("", "off"), ("track_worker_logs: off\n", "off"),
                                            ('track_worker_logs: "off"\n', "off"),
                                            ('track_worker_logs: "events"\n', "events"),
                                            ("track_worker_logs: full\n", "full")])
def test_track_worker_logs_accepts_off_events_and_full(tmp_path: Path, line: str, mode: str) -> None:
    repo = _repo(tmp_path)
    _track(repo, line)   # a bare `off` is YAML false: accepted as off
    assert gwc.load_git_workflow_config(repo)[1] is None
    assert gwc.track_worker_logs(repo) == mode


@pytest.mark.parametrize("line", ["track_worker_logs: on\n", "track_worker_logs: Full\n",
                                  'track_worker_logs: "raw"\n', "track_worker_logs: 1\n"])
def test_track_worker_logs_rejects_any_other_value(tmp_path: Path, line: str) -> None:
    repo = _repo(tmp_path)
    _track(repo, line)
    _data, err = gwc.load_git_workflow_config(repo)
    assert err and "track_worker_logs" in err
    assert gwc.track_worker_logs(repo) == "off"


def _turn(repo: Path, rec) -> None:
    wr.run(repo, rec.worker_id, wa.Launch([sys.executable, "-c", "import sys; print('out'); print('err', file=sys.stderr)"]))


def _worker_in_linked_tree(tmp_path: Path) -> tuple[Path, Path, ws.WorkerRecord]:
    repo = _repo(tmp_path)
    git(repo, "checkout", "-q", "dev")
    wt = tmp_path / "wt"
    git(repo, "worktree", "add", "-q", str(wt), "feature/rm-thing")
    return repo, wt, ws.create_record(repo, "M1.1", "generic", "m", wt, branch="feature/rm-thing")


def test_events_mode_mirrors_the_event_log_into_the_workers_checkout(tmp_path: Path) -> None:
    repo, wt, rec = _worker_in_linked_tree(tmp_path)
    _track(repo, 'track_worker_logs: "events"\n')
    _turn(repo, rec)
    logs = wt / "work" / "worker-logs" / "M1.1"
    src = ws.events_path(repo, rec.worker_id)
    assert (logs / f"{rec.worker_id}.events.jsonl").read_bytes() == src.read_bytes()
    assert not (logs / f"{rec.worker_id}.log").exists()        # the raw log only under full
    assert not (repo / "work" / "worker-logs").exists()         # the worker's checkout, not the main one
    ws.append_event(repo, rec, "message", source="orchestrator", summary="between turns")
    _track(repo, 'track_worker_logs: "full"\n')
    _turn(repo, rec)                                        # catches up from where the copy stopped
    assert (logs / f"{rec.worker_id}.events.jsonl").read_bytes() == src.read_bytes()
    assert (logs / f"{rec.worker_id}.log").read_bytes() == wr.log_path(repo, rec.worker_id).read_bytes()
    assert "err" in (logs / f"{rec.worker_id}.log").read_text()


def test_off_writes_nothing_outside_work_workers(tmp_path: Path) -> None:
    repo, wt, rec = _worker_in_linked_tree(tmp_path)
    _turn(repo, rec)   # no key: off
    assert ws.events_path(repo, rec.worker_id).is_file()
    assert not (wt / "work" / "worker-logs").exists() and not (repo / "work" / "worker-logs").exists()


@pytest.mark.slow
def test_a_leafs_own_worker_logs_neither_breach_zones_nor_block_redelegation(tmp_path: Path) -> None:
    """R2: through `delegate`, `reconcile` and `terminate`, as the coordinator drives them.

    Under the managed block's ``work/*`` every leaf's ``work/worker-logs/`` is ignored, so another
    leaf's logs no longer show as untracked or block delegation either (M22.65).
    """
    from specy_road.orchestration.workers import worker_ops as ops
    from specy_road.agent_ignores import apply_agent_ignores
    from tests.support.harness import FAKE, wait_for_worker, worker_roster

    script = tmp_path / "fake.py"
    script.write_text(FAKE)
    repo = make_review_repo(tmp_path, orchestration=worker_roster(f"{sys.executable} {script} {{prompt}} {{session}}"))
    apply_agent_ignores(repo)   # work/* ignored, work/worker-logs/ included: no re-include line
    _track(repo, 'track_worker_logs: "events"\n')
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "track worker logs")
    rec, created = ops.delegate(repo, "M1.1", "opus")
    assert created
    wait_for_worker(repo, rec.worker_id)
    own = f"work/worker-logs/M1.1/{rec.worker_id}.events.jsonl"
    assert (repo / own).is_file()
    _rec, delta = ops.reconcile(repo, rec.worker_id)
    assert own not in delta["untracked"] and own not in delta["untracked_outside_touch_zones"]
    other = repo / "work" / "worker-logs" / "M1.2" / "w-0009.events.jsonl"   # another leaf's: ignored too
    other.parent.mkdir(parents=True)
    other.write_text("{}\n")
    _rec, delta = ops.reconcile(repo, rec.worker_id)
    assert not any("worker-logs" in p for p in delta["untracked"] + delta["untracked_outside_touch_zones"])
    ops.terminate(repo, rec.worker_id)
    again, created = ops.delegate(repo, "M1.1", "opus")   # neither leaf's logs block it
    assert created and again.worker_id != rec.worker_id
    wait_for_worker(repo, again.worker_id)



# --- B1 -----------------------------------------------------------------------

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

@pytest.mark.slow
def test_a_completed_worker_still_owns_its_leaf(tmp_path: Path) -> None:
    repo, _ = make_worker_repo(tmp_path, max_workers=4)
    rec, _c = ops.delegate(repo, "M1.1", "opus")
    wait_for_worker(repo, rec.worker_id)
    ws.set_state(repo, rec, "completed", pid=None)
    again, created = ops.delegate(repo, "M1.1", "opus")
    assert not created and again.worker_id == rec.worker_id
    assert ws.active_for_node(repo, "M1.1").worker_id == rec.worker_id
    ops.terminate(repo, rec.worker_id)
    assert ws.active_for_node(repo, "M1.1") is None



def test_concurrent_reclaims_record_one_intervention(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    ws.mutate(repo, rec, lambda r: setattr(r, "provider_session_id", "sid-1"))
    ws.set_state(repo, rec, "idle", pid=None)
    ops.handoff(repo, rec.worker_id)
    results: list = []

    def go() -> None:
        try:
            results.append(ops.reclaim(repo, rec.worker_id)[0].instruction_epoch)
        except ws.WorkerError as e:
            results.append(e)

    threads = [threading.Thread(target=go) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(type(r).__name__ for r in results) == ["WorkerError", "int"]
    assert ws.load_record(repo, rec.worker_id).instruction_epoch == 1      # one intervention, not two



# --- F1 -----------------------------------------------------------------------

def test_an_op_id_binds_its_arguments(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    assert ws.begin_op(repo, "op", "message", "w-0001", {"text": "a"}) is None
    ws.complete_op(repo, "op", {"ok": 1})
    assert ws.begin_op(repo, "op", "message", "w-0001", {"text": "a"})["result"] == {"ok": 1}
    with pytest.raises(ws.WorkerError, match="different arguments"):
        ws.begin_op(repo, "op", "message", "w-0001", {"text": "b"})



def test_terminate_refuses_a_pid_it_cannot_verify(tmp_path: Path, monkeypatch) -> None:
    repo = make_review_repo(tmp_path)
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    ws.set_state(repo, rec, "running", pid=os.getpid())
    monkeypatch.setattr(wp, "_cmdline", lambda pid: None)              # ps unavailable: alive, unverified
    with pytest.raises(ws.WorkerError, match="cannot be verified"):
        ops.terminate(repo, rec.worker_id)
    monkeypatch.setattr(wp, "_cmdline", lambda pid: "python -m specy_road.worker_runner /r w-0002 {}")
    out = ops.terminate(repo, rec.worker_id)        # another worker's wrapper: not ours to signal; the record closes
    assert out.state == "terminated"



def test_terminate_closes_an_adopted_record_without_signalling(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    rec = ops.adopt(repo, "M1.1", "claude-code", "aaaaaaaa-0000-4000-8000-000000000001")
    ws.set_state(repo, rec, "idle", pid=os.getpid())
    out = ops.terminate(repo, rec.worker_id)
    assert out.state == "terminated"
    assert "not signalled" in ws.events_since(repo, rec.worker_id)[-1].summary



def test_reclaim_keeps_the_prompt_verbatim(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    ws.mutate(repo, rec, lambda r: setattr(r, "provider_session_id", "sid-1"))
    ws.set_state(repo, rec, "idle", pid=None)
    ops.handoff(repo, rec.worker_id)
    long = "x" * 600
    wl.record_hook_prompt(repo, "sid-1", long)
    _rec, detail = ops.reclaim(repo, rec.worker_id)
    assert detail["prompts"] == [long]



# --- Gemini F2 ----------------------------------------------------------------

# One test per finding: reconcile judges the worker's whole lifetime; READY must be at the
# worktree's HEAD; routing reads the roster from the integration branch; the guard follows env -S,
# nested $(), attached -C, --git-dir, long wrapper options, timeout, xargs-from-stdin and
# configured aliases, and refuses a non-string hook command; a dead wrapper fails on
# message/handoff; a skipped skill gets no link and a foreign directory is never removed; the
# nested AGENTS.md report carries its prefix; rounds are persisted; a malformed custom cli raises;
# event sequences survive a crash; adopt is atomic; hook prompts are verbatim; the verifier pins
# its address; round one hides the roadmap digest; an invalid profile is a staffing error; a
# mismatched slug is refused.

def test_a_crashed_running_worker_cannot_be_handed_off_and_is_recorded_failed_before_a_message(tmp_path: Path) -> None:
    repo, _ = make_worker_repo(tmp_path)
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    ws.mutate(repo, rec, lambda r: setattr(r, "provider_session_id", "sid-1"))
    ws.set_state(repo, rec, "running", pid=999999)
    with pytest.raises(ws.WorkerError, match="failed"):
        ops.handoff(repo, rec.worker_id)
    assert ws.load_record(repo, rec.worker_id).state == "failed"
    ws.set_state(repo, rec, "running", pid=999999)
    ops.message(repo, rec.worker_id, "hi")   # the crash is recorded, then its session resumes (M11.2)
    types = [e.type for e in ws.events_since(repo, rec.worker_id)]
    assert types.count("error") == 2 and types.index("message") > types.index("error")
    assert wait_for_worker(repo, rec.worker_id).state == "idle"



# --- Sol B4 ----------------------------------------------------------------------

def test_event_sequences_survive_a_record_that_lags_the_log(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    ws.append_event(repo, rec, "output", source="worker", summary="written before crash")
    ws.mutate(repo, rec, lambda r: setattr(r, "last_event_seq", 1))      # the crash: log says 2, record says 1
    ws.append_event(repo, rec, "error", source="system", summary="recovery")
    seqs = [e.seq for e in ws.events_since(repo, rec.worker_id)]
    assert seqs == [1, 2, 3]



# --- Sol B5 ----------------------------------------------------------------------

def test_a_platform_without_a_file_lock_refuses_worker_mutations(tmp_path: Path, monkeypatch) -> None:
    import builtins

    from specy_road.orchestration.workers import worker_lock

    real_import = builtins.__import__

    def no_locks(name, *a, **k):
        if name in ("fcntl", "msvcrt"):
            raise ImportError(name)
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", no_locks)
    with pytest.raises(ws.WorkerError, match="exclusive file lock"), worker_lock.workers_lock(tmp_path):
        pass



# --- Sol B6 ----------------------------------------------------------------------

def test_adopt_is_one_transaction(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    rec = ops.adopt(repo, "M1.1", "claude-code", "aaaaaaaa-0000-4000-8000-000000000001")
    types = [e.type for e in ws.events_since(repo, rec.worker_id)]
    assert types[-1] == "adopted" and ws.load_record(repo, rec.worker_id).checkpoint is not None



# --- Sol B7 ----------------------------------------------------------------------

def test_hook_prompts_are_stored_whole(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    ws.mutate(repo, rec, lambda r: setattr(r, "provider_session_id", "sid-1"))
    ws.set_state(repo, rec, "idle", pid=None)
    ops.handoff(repo, rec.worker_id)
    long = "y" * 2501
    wl.record_hook_prompt(repo, "sid-1", long)
    _rec, detail = ops.reclaim(repo, rec.worker_id)
    assert detail["prompts"] == [long]



def _hook(repo: Path, fmt: str, payload: dict) -> int:
    sys.stdin = io.StringIO(json.dumps(payload))
    try:
        return run_worker_cli("worker", "hook", "--format", fmt, "--repo-root", str(repo))
    finally:
        sys.stdin = sys.__stdin__



# --- B13 -----------------------------------------------------------------------

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

def test_resume_commands_are_shell_quoted_and_bad_ids_refused(tmp_path: Path) -> None:
    assert wsess.render_command(["claude", "--resume", "sid; touch /tmp/forged"]) == \
        "claude --resume 'sid; touch /tmp/forged'"
    repo = make_review_repo(tmp_path)
    with pytest.raises(ws.WorkerError, match="metacharacters"):
        ops.adopt(repo, "M1.1", "claude-code", "sid; touch /tmp/forged")
    with pytest.raises(ws.WorkerError, match="not a UUID"):
        ops.adopt(repo, "M1.1", "codex", "thr-1")
    assert ops.adopt(repo, "M1.1", "cursor", "chat_01:abc-DEF").provider_session_id == "chat_01:abc-DEF"
    # An id the harness output chose is refused at use, not rendered into a command.
    rec = idle_record(repo, "M1.2", sid="$(touch /tmp/forged)")
    with pytest.raises(ws.WorkerError, match="metacharacters"):
        ops.handoff(repo, rec.worker_id)
    with pytest.raises(ws.WorkerError, match="metacharacters"):
        ops.message(repo, rec.worker_id, "hi")
    assert ws.load_record(repo, rec.worker_id).lease["holder"] == "broker"



# --- F10 -----------------------------------------------------------------------

def test_hook_matches_by_harness_and_refuses_ambiguity(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path)
    a = idle_record(repo, "M1.1", "claude-code", "same-id")
    b = idle_record(repo, "M1.2", "cursor", "same-id")
    ops.handoff(repo, a.worker_id)
    ops.handoff(repo, b.worker_id)
    assert _hook(repo, "cursor", {"conversation_id": "same-id", "prompt": "cursor human"}) == 0
    assert not ops.interventions_path(repo, a.worker_id).is_file()
    assert "cursor human" in ops.interventions_path(repo, b.worker_id).read_text()
    with pytest.raises(ws.WorkerError, match="ambiguous"):
        ww.record_hook_prompt(repo, "same-id", "no harness given")
    assert _hook(repo, "claude-code", {"session_id": "same-id", "prompt": "claude human"}) == 0
    assert "claude human" in ops.interventions_path(repo, a.worker_id).read_text()



def test_hook_witness_does_not_wait_on_a_busy_lock(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    rec = idle_record(repo)
    ops.handoff(repo, rec.worker_id)
    release = threading.Event()
    taken = threading.Event()

    def hold() -> None:
        with ws.workers_lock(repo):
            taken.set()
            release.wait(10)
    t = threading.Thread(target=hold, daemon=True)
    t.start()
    taken.wait(5)
    t0 = time.monotonic()
    assert ww.record_hook_prompt(repo, "sid-1", "while busy", harness="claude-code", timeout=0.3) is None
    assert time.monotonic() - t0 < 2
    release.set()
    t.join(5)
    assert ww.record_hook_prompt(repo, "sid-1", "after", harness="claude-code", timeout=0.3) is not None
    _r, d = ops.reclaim(repo, rec.worker_id)
    assert d["prompts"] == ["after"]



# --- F11 (c) ---------------------------------------------------------------------

def test_a_crashed_reclaim_is_repaired_once_not_repeated(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    rec = idle_record(repo)
    ops.handoff(repo, rec.worker_id)
    real = wl.append_event
    with mock.patch.object(wl, "append_event", side_effect=OSError("crash after the record moved")):
        with pytest.raises(OSError):
            ops.reclaim(repo, rec.worker_id)
    mid = ws.load_record(repo, rec.worker_id)
    assert mid.instruction_epoch == 1 and mid.lease["holder"] == "broker" and mid.state == "idle"
    wl.append_event = real
    rec2, d = ops.reclaim(repo, rec.worker_id)          # the retry repairs the events
    evs = [e for e in ws.events_since(repo, rec.worker_id) if e.type in ("intervention", "reclaim")]
    assert rec2.instruction_epoch == 1 and [e.type for e in evs] == ["intervention", "reclaim"]
    assert evs[0].epoch == 1 and "repaired" in evs[0].summary
    with pytest.raises(ws.WorkerError, match="not handed off"):
        ops.reclaim(repo, rec.worker_id)                 # and a third call is refused, not repeated
    assert ws.load_record(repo, rec.worker_id).instruction_epoch == 1



def test_handoff_and_reclaim_move_the_record_in_one_write(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    rec = idle_record(repo)
    saves: list[tuple[str, str, int]] = []
    real = ws.save_record

    def spy(root, r):
        saves.append((r.lease["holder"], r.state, r.instruction_epoch))
        return real(root, r)
    with mock.patch.object(ws, "save_record", side_effect=spy):
        ops.handoff(repo, rec.worker_id)
        ops.reclaim(repo, rec.worker_id)
    # No save ever shows a half-moved record: human+handed_off, then broker+idle+epoch 1, never a mix.
    assert all(s in {("broker", "idle", 0), ("human", "handed_off", 0), ("broker", "idle", 1)} for s in saves)
    assert ("human", "idle", 0) not in saves and ("broker", "handed_off", 0) not in saves



# --- F11 (d) ---------------------------------------------------------------------

def test_sync_ack_runs_under_the_workers_lock(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    release = threading.Event()
    taken = threading.Event()
    done: list[float] = []

    def hold() -> None:
        with ws.workers_lock(repo):
            taken.set()
            release.wait(10)
    threading.Thread(target=hold, daemon=True).start()
    taken.wait(5)
    t = threading.Thread(target=lambda: (wrc.sync(repo, ack=True), done.append(time.monotonic())))
    t.start()
    time.sleep(0.5)
    assert not done                                   # blocked behind the other writer
    t0 = time.monotonic()
    before = datetime.now(timezone.utc).replace(microsecond=0)
    release.set()
    t.join(5)
    assert done and done[0] >= t0
    marks = yaml.safe_load((ws.workers_dir(repo) / "sync.yaml").read_text())
    last = ws.load_record(repo, rec.worker_id).last_event_seq
    acked_at = marks.get(rec.worker_id, {}).get("acked_at")
    assert isinstance(acked_at, str) and before <= datetime.fromisoformat(acked_at) <= datetime.now(timezone.utc)
    assert marks == {rec.worker_id: {"seq": last, "acked_at": acked_at}}   # exactly these fields, nothing else
    assert wrc.sync(repo) == []                                 # the mark still reads as acknowledged
    # A file from before acked_at was recorded (a bare integer per worker) is still a mark.
    (ws.workers_dir(repo) / "sync.yaml").write_text(f"{rec.worker_id}: {last}\n")
    assert wrc.sync_marks(repo) == {rec.worker_id: {"seq": last, "acked_at": None}} and wrc.sync(repo) == []



# One test per finding: records survive a concurrent writer (the wrapper no longer writes a stale
# copy back), two delegates on one leaf launch once, terminate reaches the harness and its
# children, an op id names one operation, an older attempt's READY does not complete a new worker,
# and the harness does not inherit the wrapper's PYTHONPATH.

@pytest.mark.slow
def test_a_flag_set_while_the_wrapper_streams_survives(tmp_path: Path) -> None:
    repo, _script = make_worker_repo(tmp_path)
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
    wait_for_worker(repo, rec.worker_id)
    final = ws.load_record(repo, rec.worker_id)
    assert ws.FLAG_RECONCILE in final.flags
    seqs = [e.seq for e in ws.events_since(repo, rec.worker_id)]
    assert seqs == sorted(set(seqs)) and final.last_event_seq == seqs[-1]



def test_terminate_refuses_a_handed_off_worker(tmp_path: Path) -> None:
    repo, _ = make_worker_repo(tmp_path)
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    ws.set_lease(repo, rec, "human")
    with pytest.raises(ws.WorkerError, match="reclaim"):
        ops.terminate(repo, rec.worker_id)



def test_an_op_id_names_one_operation(tmp_path: Path) -> None:
    repo, _ = make_worker_repo(tmp_path)
    assert ws.begin_op(repo, "X1", "reconcile", "w-0001") is None
    ws.complete_op(repo, "X1", {"ok": True})
    assert ws.begin_op(repo, "X1", "reconcile", "w-0001")["result"] == {"ok": True}
    with pytest.raises(ws.WorkerError, match="names one operation"):
        ws.begin_op(repo, "X1", "terminate", "w-0001")
    with pytest.raises(ws.WorkerError, match="names one operation"):
        ws.begin_op(repo, "X1", "reconcile", "w-0002")



# One test per finding: a prompt containing `<prompt>` cannot break out of the shell quoting; the
# session id chosen up front survives the spawn; a completed worker can take a review `block` as a
# message and a turn's READY is judged against that turn; a linked worktree gets the brief; the
# guard scopes tree-only commands to this worktree and sees `checkout -f`, `restore <path>`, brace
# groups, `eval` and `$(…)`; an op id is bound to its target; handoff refuses a closed worker;
# hook prompts are attributed by line, not by second; adopt refuses a duplicate; reconcile treats
# an unbuildable prompt as a contract change; Codex resume keeps its sandbox; reviews_root stays
# inside a nested project; the CGNAT range is off-host.

def test_handoff_refuses_a_closed_worker(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    ws.mutate(repo, rec, lambda r: setattr(r, "provider_session_id", "sid-1"))
    ops.terminate(repo, rec.worker_id)
    with pytest.raises(ws.WorkerError, match="terminated"):
        ops.handoff(repo, rec.worker_id)
    assert ws.load_record(repo, rec.worker_id).state == "terminated"



def test_hook_prompts_are_attributed_by_line_and_only_under_a_human_lease(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    ws.mutate(repo, rec, lambda r: setattr(r, "provider_session_id", "sid-1"))
    assert ops.record_hook_prompt(repo, "sid-1", "broker prompt") is None    # not an intervention
    ws.set_state(repo, rec, "idle", pid=None)
    ops.handoff(repo, rec.worker_id)
    ops.record_hook_prompt(repo, "sid-1", "human says hi")
    rec, detail = ops.reclaim(repo, rec.worker_id)
    assert detail["prompts"] == ["human says hi"] and ws.FLAG_EXTERNAL not in rec.flags
    ops.handoff(repo, rec.worker_id)                                        # same second: the old line does not count
    rec, detail = ops.reclaim(repo, rec.worker_id)
    assert detail["prompts"] == [] and ws.FLAG_EXTERNAL in rec.flags



def test_adopt_refuses_a_second_worker_on_the_leaf(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    ops.adopt(repo, "M1.1", "claude-code", "aaaaaaaa-0000-4000-8000-000000000001")
    with pytest.raises(ws.WorkerError, match="already has an active worker"):
        ops.adopt(repo, "M1.1", "claude-code", "aaaaaaaa-0000-4000-8000-000000000002")
