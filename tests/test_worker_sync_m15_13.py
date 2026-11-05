"""M15.13: worker sync --until, collapsed tool-use output, rework after completed, ready-only resume."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest

from specy_road import worker_state as ws
from specy_road.bundled_scripts.worker_cli_render import sync_event_lines
from specy_road.worker_runner_ready import READY_ONLY_PROMPT
from tests.review_repo_helpers import git
from tests.test_rework_findings_in_prompt import file_review
from tests.worker_cli_helpers import run_worker_cli, wait_for_worker
from tests.worker_repo_helpers import make_worker_repo

_UNTIL_VALUES = ("completion", "error", "intervention", "completion,error", "error,intervention")


def _idle_rec(repo: Path) -> ws.WorkerRecord:
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    ws.set_state(repo, rec, "idle", pid=None)
    return rec


def _ack_all(repo: Path) -> None:
    run_worker_cli("worker", "sync", "--wait", "--ack", "--repo-root", str(repo))


@pytest.mark.parametrize("until", _UNTIL_VALUES)
def test_sync_wait_until_exits_0_when_the_condition_is_met(tmp_path: Path, capsys, until: str) -> None:
    repo, _ = make_worker_repo(tmp_path)
    rec = _idle_rec(repo)
    _ack_all(repo)
    capsys.readouterr()
    want = {t.strip() for t in until.split(",")}
    if "completion" in want:
        ws.append_event(repo, rec, "completion", source="worker", summary="exit 0; READY file present",
                        detail={"exit": 0, "ready": True})
    elif "error" in want:
        ws.append_event(repo, rec, "error", source="worker", summary="exit 1", detail={"exit": 1})
    else:
        ws.append_event(repo, rec, "intervention", source="human", authority="human_authoritative", summary="stop")
    assert run_worker_cli("worker", "sync", "--wait", "--until", until, "--timeout", "5",
                          "--json", "--repo-root", str(repo)) == 0
    evs = json.loads(capsys.readouterr().out)["workers"][0]["events"]
    assert evs[-1]["type"] in want


@pytest.mark.parametrize("until", ("completion", "error", "intervention"))
def test_sync_wait_until_exits_2_on_timeout_with_no_events(tmp_path: Path, capsys, until: str) -> None:
    repo, _ = make_worker_repo(tmp_path)
    _idle_rec(repo)
    _ack_all(repo)
    capsys.readouterr()
    assert run_worker_cli("worker", "sync", "--wait", "--until", until, "--timeout", "0.3",
                          "--repo-root", str(repo)) == 2
    assert "No new worker events." in capsys.readouterr().out


@pytest.mark.parametrize("until", ("completion", "error", "intervention"))
def test_sync_wait_until_exits_2_on_timeout_with_unmatched_events(tmp_path: Path, capsys, until: str) -> None:
    repo, _ = make_worker_repo(tmp_path)
    rec = _idle_rec(repo)
    _ack_all(repo)
    capsys.readouterr()
    ws.append_event(repo, rec, "output", source="worker", summary="(tool use)")
    assert run_worker_cli("worker", "sync", "--wait", "--until", until, "--timeout", "0.3",
                          "--repo-root", str(repo)) == 2
    out = capsys.readouterr().out
    assert "(tool use)" in out or "tool uses" in out


def test_sync_wait_until_completion_waits_past_output_before_completion(tmp_path: Path, capsys) -> None:
    repo, _ = make_worker_repo(tmp_path)
    rec = _idle_rec(repo)
    _ack_all(repo)
    capsys.readouterr()
    for _ in range(3):
        ws.append_event(repo, rec, "output", source="worker", summary="(tool use)")
    threading.Timer(0.4, lambda: ws.append_event(repo, rec, "completion", source="worker",
                                                   summary="exit 0; READY file present",
                                                   detail={"exit": 0, "ready": True})).start()
    t0 = time.monotonic()
    assert run_worker_cli("worker", "sync", "--wait", "--until", "completion", "--timeout", "10",
                          "--json", "--repo-root", str(repo)) == 0
    assert time.monotonic() - t0 >= 0.35
    evs = json.loads(capsys.readouterr().out)["workers"][0]["events"]
    assert evs[-1]["type"] == "completion"


def test_sync_collapses_consecutive_tool_use_lines(tmp_path: Path, capsys) -> None:
    repo, _ = make_worker_repo(tmp_path)
    rec = _idle_rec(repo)
    for _ in range(6):
        ws.append_event(repo, rec, "output", source="worker", summary="(tool use)")
    run_worker_cli("worker", "sync", "--repo-root", str(repo))
    out = capsys.readouterr().out
    assert " output: 6 tool uses" in out
    assert "-#" in out
    assert out.count("(tool use)") == 0


def test_sync_verbose_shows_each_tool_use(tmp_path: Path, capsys) -> None:
    repo, _ = make_worker_repo(tmp_path)
    rec = _idle_rec(repo)
    ws.append_event(repo, rec, "output", source="worker", summary="(tool use)")
    ws.append_event(repo, rec, "output", source="worker", summary="(tool use)")
    run_worker_cli("worker", "sync", "--verbose", "--repo-root", str(repo))
    out = capsys.readouterr().out
    assert out.count("(tool use)") == 2


def test_completion_missing_ready_offers_ready_only_resume() -> None:
    lines = sync_event_lines([], [{"seq": 3, "type": "completion", "source": "worker",
                                     "summary": "exit 0; READY file missing",
                                     "detail": {"exit": 0, "ready": False}}], "w-0001")
    assert any("worker resume w-0001 --ready-only" in line for line in lines)


def test_resume_ready_only_writes_the_prompt_file_via_the_cli(tmp_path: Path, capsys) -> None:
    repo, _ = make_worker_repo(tmp_path)
    run_worker_cli("worker", "delegate", "M1.1", "--model", "opus", "--repo-root", str(repo))
    rec = wait_for_worker(repo, "w-0001")
    capsys.readouterr()
    assert run_worker_cli("worker", "resume", rec.worker_id, "--ready-only", "--repo-root", str(repo)) == 0
    paths = sorted((repo / "work").glob(f"prompt-{rec.worker_id}-ready-only-*.md"))
    assert len(paths) == 1
    assert paths[0].read_text(encoding="utf-8") == READY_ONLY_PROMPT
    wait_for_worker(repo, rec.worker_id)


def test_delegate_rework_proceeds_when_the_leaf_worker_is_completed(tmp_path: Path, capsys) -> None:
    repo, _ = make_worker_repo(tmp_path)

    rec = ws.create_record(repo, "M1.1", "claude-code", "grok", repo)
    ws.set_state(repo, rec, "completed", pid=None)
    ws.mutate(repo, rec, lambda r: setattr(r, "provider_session_id", "s1"))
    file_review(repo, "sol", git(repo, "rev-parse", "HEAD"), "block", ["fix it"])
    assert run_worker_cli("worker", "delegate", "M1.1", "--model", "opus", "--rework", "--json",
                          "--repo-root", str(repo)) == 0
    captured = capsys.readouterr()
    out = json.loads(captured.out)
    assert out["created"] is True and out["worker_id"] == "w-0002" and out["model"] == "opus"
    assert ws.load_record(repo, "w-0001").state == "terminated"
    assert "w-0001's last message (grok, completed)" in captured.err
    launched = wait_for_worker(repo, "w-0002")
    assert launched.state == "idle" and launched.model == "opus"
    assert ws.events_since(repo, "w-0002")[-1].type == "completion"


def test_delegate_rework_with_completed_only_launches_a_fresh_worker(tmp_path: Path, capsys) -> None:
    repo, _ = make_worker_repo(tmp_path)
    rec = ws.create_record(repo, "M1.1", "claude-code", "grok", repo)
    ws.set_state(repo, rec, "completed", pid=None)
    ws.append_event(repo, rec, "turn_completed", source="worker", summary="done",
                    detail={"message": "Finished impl; forgot READY."})
    assert run_worker_cli("worker", "delegate", "M1.1", "--model", "opus", "--rework", "--json",
                          "--repo-root", str(repo)) == 0
    captured = capsys.readouterr()
    out = json.loads(captured.out)
    assert out["created"] is True and out["worker_id"] == "w-0002" and out["model"] == "opus"
    assert "w-0001's last message (grok, completed)" in captured.err
    wait_for_worker(repo, "w-0002")


@pytest.mark.parametrize(
    "state",
    ("completed", "failed", "terminated"),
)
def test_rework_accepts_each_ended_worker_state_without_a_block(tmp_path: Path, state: str) -> None:
    repo, _ = make_worker_repo(tmp_path)
    rec = ws.create_record(repo, "M1.1", "claude-code", "grok", repo)
    ws.set_state(repo, rec, state, pid=None)
    assert run_worker_cli("worker", "delegate", "M1.1", "--model", "opus", "--rework", "--repo-root", str(repo)) == 0
    wait_for_worker(repo, "w-0002")


def test_rework_refuses_idle_worker_without_a_block(tmp_path: Path, capsys) -> None:
    repo, _ = make_worker_repo(tmp_path)
    rec = ws.create_record(repo, "M1.1", "claude-code", "grok", repo)
    ws.set_state(repo, rec, "idle", pid=None)
    assert run_worker_cli("worker", "delegate", "M1.1", "--model", "opus", "--rework", "--repo-root", str(repo)) == 1
    assert "still active on M1.1 (idle)" in capsys.readouterr().err


def test_rework_offline_does_not_delete_completed_worker_leases(tmp_path: Path, monkeypatch) -> None:
    from specy_road import worker_lease as wl
    from tests.worker_lease_helpers import remote_and_clone, remote_leases

    repo, _ = make_worker_repo(tmp_path)
    remote, _ = remote_and_clone(tmp_path, repo)
    run_worker_cli("worker", "delegate", "M1.1", "--model", "opus", "--repo-root", str(repo))
    rec = wait_for_worker(repo, "w-0001")
    ws.set_state(repo, rec, "completed", pid=None)
    before = remote_leases(remote)
    assert any(rec.worker_id in ref for ref in before)
    pushes: list[list[str]] = []
    real_run = wl.run

    def track(args, cwd, **kw):
        pushes.append(list(args))
        return real_run(args, cwd, **kw)

    monkeypatch.setattr(wl, "run", track)
    assert run_worker_cli("worker", "delegate", "M1.1", "--model", "opus", "--rework", "--offline",
                          "--repo-root", str(repo)) == 0
    assert remote_leases(remote) == before
    assert not any(a[0:2] == ["push", "--quiet"] and "--delete" in a for a in pushes)
    wait_for_worker(repo, "w-0002")


@pytest.mark.parametrize(
    ("extra_first", "extra_second"),
    (
        (("--ready-only",), ()),
        ((), ("--ready-only",)),
        (("--offline",), ()),
        ((), ("--offline",)),
        (("--ready-only",), ("--offline",)),
        (("--offline",), ("--ready-only",)),
    ),
)
def test_resume_op_id_refuses_when_offline_or_ready_only_toggles(tmp_path: Path, capsys, extra_first, extra_second) -> None:
    repo, _ = make_worker_repo(tmp_path)
    run_worker_cli("worker", "delegate", "M1.1", "--model", "opus", "--repo-root", str(repo))
    rec = wait_for_worker(repo, "w-0001")
    capsys.readouterr()
    base = ("worker", "resume", rec.worker_id, "--op-id", "resume-op", "--repo-root", str(repo))
    assert run_worker_cli(*base, *extra_first) == 0
    wait_for_worker(repo, rec.worker_id)
    capsys.readouterr()
    assert run_worker_cli(*base, *extra_second) != 0
    assert "ran with different arguments" in capsys.readouterr().err
