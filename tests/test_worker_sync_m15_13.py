"""M15.13: worker sync --until, collapsed tool-use output, rework after completed, ready-only resume."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from specy_road import worker_state as ws
from specy_road.bundled_scripts.worker_cli_render import sync_event_lines
from specy_road.worker_ops_message import resume
from specy_road.worker_runner_ready import READY_ONLY_PROMPT
from tests.test_worker_cli import _repo, run_worker_cli, wait_for_worker


def test_sync_wait_until_completion_skips_output_events(tmp_path: Path, capsys) -> None:
    repo, _ = _repo(tmp_path)
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    ws.set_state(repo, rec, "idle", pid=None)
    run_worker_cli("worker", "sync", "--wait", "--ack", "--repo-root", str(repo))
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
    assert any(e["type"] == "output" for e in evs)


def test_sync_collapses_consecutive_tool_use_lines(tmp_path: Path, capsys) -> None:
    repo, _ = _repo(tmp_path)
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    ws.set_state(repo, rec, "idle", pid=None)
    for _ in range(6):
        ws.append_event(repo, rec, "output", source="worker", summary="(tool use)")
    run_worker_cli("worker", "sync", "--repo-root", str(repo))
    out = capsys.readouterr().out
    assert " output: 6 tool uses" in out
    assert "-#" in out
    assert out.count("#") >= 2
    assert out.count("(tool use)") == 0


def test_sync_verbose_shows_each_tool_use(tmp_path: Path, capsys) -> None:
    repo, _ = _repo(tmp_path)
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    ws.set_state(repo, rec, "idle", pid=None)
    ws.append_event(repo, rec, "output", source="worker", summary="(tool use)")
    ws.append_event(repo, rec, "output", source="worker", summary="(tool use)")
    run_worker_cli("worker", "sync", "--verbose", "--repo-root", str(repo))
    out = capsys.readouterr().out
    assert " tool uses" not in out or "output: 2 tool uses" not in out.replace("  #", "")
    assert out.count("(tool use)") == 2


def test_completion_missing_ready_offers_ready_only_resume() -> None:
    lines = sync_event_lines([], [{"seq": 3, "type": "completion", "source": "worker",
                                     "summary": "exit 0; READY file missing",
                                     "detail": {"exit": 0, "ready": False}}], "w-0001")
    assert any("worker resume w-0001 --ready-only" in line for line in lines)


def test_resume_ready_only_uses_the_fixed_prompt(tmp_path: Path, monkeypatch) -> None:
    repo, _ = _repo(tmp_path)
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    ws.set_state(repo, rec, "idle", pid=None)
    ws.mutate(repo, rec, lambda r: setattr(r, "provider_session_id", "sess-1"))
    captured: list[str] = []

    def fake_send(root, r, text, kind, offline=False, *, no_queue=False):
        captured.extend([text, kind])
        return r

    monkeypatch.setattr("specy_road.worker_ops_message._send", fake_send)
    resume(repo, rec.worker_id, ready_only=True)
    assert captured[0] == READY_ONLY_PROMPT
    assert captured[1] == "ready-only"


def test_delegate_rework_proceeds_when_the_leaf_worker_is_completed(tmp_path: Path, capsys) -> None:
    repo, _ = _repo(tmp_path)
    from tests.review_repo_helpers import git
    from tests.test_rework_findings_in_prompt import file_review

    rec = ws.create_record(repo, "M1.1", "claude-code", "grok", repo)
    ws.set_state(repo, rec, "completed", pid=None)
    ws.mutate(repo, rec, lambda r: setattr(r, "provider_session_id", "s1"))
    file_review(repo, "sol", git(repo, "rev-parse", "HEAD"), "block", ["fix it"])
    assert run_worker_cli("worker", "delegate", "M1.1", "--model", "opus", "--rework", "--repo-root", str(repo)) == 0
    captured = capsys.readouterr()
    assert "w-0001 on M1.1 (completed)" in captured.err
