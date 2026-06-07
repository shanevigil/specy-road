"""Tests for the grind-session loop orchestrator (``grind_session``)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import grind_session as gs

REPO = Path(__file__).resolve().parent.parent
DOGFOOD = REPO / "tests" / "fixtures" / "specy_road_dogfood"
from grind_session_events import (
    EXIT_BLOCKED,
    EXIT_GENERIC,
    EXIT_NO_LEAVES,
    EXIT_OK,
    EXIT_PICKUP_FAILED,
    EXIT_PRE_FINISH_FAILED,
)
from session_plan import BlockedLeaf, SessionPlan, Wave


def _node(nid, codename=None):
    return {"id": nid, "codename": codename or f"cn-{nid.lower().replace('.', '-')}"}


def _plan(ready=None, blocked=None, active=None):
    ready = ready or []
    return SessionPlan(
        under=None,
        ready=list(ready),
        blocked=list(blocked or []),
        active=list(active or []),
        closed=[],
        gated=[],
        gates_open=[],
        needs_codename=[],
        waves=[Wave(index=0, node_ids=list(ready))] if ready else [],
        parallel_batches=[list(ready)] if ready else [],
        totals={"ready": len(ready)},
    )


class _Harness:
    """Drives a scripted sequence of plans and records subprocess calls."""

    def __init__(self, monkeypatch, plans, *, pickup_rc=0, finish_rc=0,
                 implement_rc=0, pre_finish_rc=0):
        self.plans = list(plans)
        self.idx = 0
        self.cli_calls: list[list[str]] = []
        self.shell_calls: list[str] = []
        self.implement_rc = implement_rc
        self.pre_finish_rc = pre_finish_rc
        self.pickup_rc = pickup_rc
        self.finish_rc = finish_rc

        def fake_gather(repo_root, under):
            plan = self.plans[min(self.idx, len(self.plans) - 1)]
            nodes = [_node(nid) for nid in plan.ready]
            return nodes, {"version": 1, "entries": []}, plan

        def fake_run_cli(repo_root, cli_args):
            self.cli_calls.append(cli_args)
            if cli_args[0] == "do-next-available-task":
                return self.pickup_rc
            if cli_args[0] == "finish-this-task":
                # advance to the next scripted plan after a finish
                self.idx += 1
                return self.finish_rc
            return 0

        def fake_run_shell(cmd, env, repo_root):
            self.shell_calls.append(cmd)
            # distinguish pre-finish vs implement by env marker is not needed;
            # implement-cmd and pre-finish-cmd use different stored values.
            return 0

        def fake_current_branch(repo_root):
            plan = self.plans[min(self.idx, len(self.plans) - 1)]
            nid = plan.ready[0]
            return f"feature/rm-cn-{nid.lower().replace('.', '-')}"

        def fake_resolve(repo_root, branch, fallback):
            return fallback

        def fake_wait(repo_root, rel, timeout):
            return self.implement_rc == 0

        monkeypatch.setattr(gs, "gather_plan", fake_gather)
        monkeypatch.setattr(gs, "_run_cli", fake_run_cli)
        monkeypatch.setattr(gs, "_run_shell", fake_run_shell)
        monkeypatch.setattr(gs, "_current_branch", fake_current_branch)
        monkeypatch.setattr(gs, "_resolve_picked", fake_resolve)
        monkeypatch.setattr(gs, "_wait_for_signal", fake_wait)


def _run(argv):
    from grind_session_args import parse_grind_session_args

    args = parse_grind_session_args(argv)
    return gs.run_session(args)


def _events(capsys):
    out = capsys.readouterr().out.strip().splitlines()
    return [json.loads(line) for line in out if line.strip()]


# ---------------------------------------------------------------------------
# Plan mode
# ---------------------------------------------------------------------------


def test_plan_mode_emits_plan_and_no_git(monkeypatch, capsys):
    h = _Harness(monkeypatch, [_plan(ready=["M1.1"], blocked=[
        BlockedLeaf("M1.2", "cn", ["M1.1"], "dependency")])])
    code = _run(["--plan", "--json", "--repo-root", "/tmp/x"])
    assert code == EXIT_OK
    evs = _events(capsys)
    assert evs[0]["event"] == "plan"
    assert evs[0]["ready"] == ["M1.1"]
    assert h.cli_calls == []  # no pickup/finish in plan mode


# ---------------------------------------------------------------------------
# Loop happy paths
# ---------------------------------------------------------------------------


def test_loop_hook_mode_max_leaves(monkeypatch, capsys):
    plans = [_plan(ready=["M1.1"]), _plan(ready=["M1.2"]), _plan(ready=["M1.3"])]
    h = _Harness(monkeypatch, plans)
    code = _run(["--implement-mode", "hook", "--implement-cmd", "true",
                 "--max-leaves", "2", "--json", "--repo-root", "/tmp/x"])
    assert code == EXIT_OK
    evs = _events(capsys)
    finished = [e for e in evs if e["event"] == "finished"]
    assert [e["node_id"] for e in finished] == ["M1.1", "M1.2"]
    assert evs[-1] == {"event": "stopped", "reason": "max_leaves", "node_id": "M1.2"}
    pickups = [c for c in h.cli_calls if c[0] == "do-next-available-task"]
    assert len(pickups) == 2


def test_loop_until_stops_after_node(monkeypatch, capsys):
    plans = [_plan(ready=["M1.1"]), _plan(ready=["M1.2"]), _plan(ready=["M1.3"])]
    _Harness(monkeypatch, plans)
    code = _run(["--implement-mode", "hook", "--implement-cmd", "true",
                 "--until", "M1.2", "--json", "--repo-root", "/tmp/x"])
    assert code == EXIT_OK
    evs = _events(capsys)
    assert evs[-1] == {"event": "stopped", "reason": "until_reached", "node_id": "M1.2"}


def test_loop_runs_until_no_work(monkeypatch, capsys):
    plans = [_plan(ready=["M1.1"]), _plan(ready=[])]
    _Harness(monkeypatch, plans)
    code = _run(["--implement-mode", "hook", "--implement-cmd", "true",
                 "--json", "--repo-root", "/tmp/x"])
    assert code == EXIT_OK
    evs = _events(capsys)
    assert evs[-1]["event"] == "stopped"
    assert evs[-1]["reason"] == "no_work"


# ---------------------------------------------------------------------------
# Stop / failure exit codes
# ---------------------------------------------------------------------------


def test_blocked_only_exits_3(monkeypatch, capsys):
    plan = _plan(ready=[], blocked=[BlockedLeaf("M11.1", "cn", ["M10.5"], "dependency")])
    h = _Harness(monkeypatch, [plan])
    code = _run(["--implement-mode", "hook", "--implement-cmd", "true",
                 "--json", "--repo-root", "/tmp/x"])
    assert code == EXIT_BLOCKED
    evs = _events(capsys)
    assert evs[-1]["event"] == "blocked"
    assert evs[-1]["waiting_on"] == ["M10.5"]
    assert h.cli_calls == []  # never attempted pickup


def test_no_actionable_leaves_exits_2(monkeypatch, capsys):
    _Harness(monkeypatch, [_plan(ready=[])])
    code = _run(["--implement-mode", "hook", "--implement-cmd", "true",
                 "--json", "--repo-root", "/tmp/x"])
    assert code == EXIT_NO_LEAVES


def test_pre_finish_failure_exits_4_and_skips_finish(monkeypatch, capsys):
    h = _Harness(monkeypatch, [_plan(ready=["M1.1"])])

    def failing_shell(cmd, env, repo_root):
        h.shell_calls.append(cmd)
        return 2 if cmd == "make test" else 0  # only the pre-finish hook fails

    monkeypatch.setattr(gs, "_run_shell", failing_shell)
    code = _run(["--implement-mode", "hook", "--implement-cmd", "true",
                 "--pre-finish-cmd", "make test", "--json", "--repo-root", "/tmp/x"])
    assert code == EXIT_PRE_FINISH_FAILED
    # finish-this-task must NOT have been called.
    assert not any(c[0] == "finish-this-task" for c in h.cli_calls)
    evs = _events(capsys)
    assert evs[-1]["event"] == "hook_failed"
    assert evs[-1]["phase"] == "pre_finish"


def test_pickup_failure_exits_5(monkeypatch, capsys):
    h = _Harness(monkeypatch, [_plan(ready=["M1.1"])], pickup_rc=1)
    code = _run(["--implement-mode", "hook", "--implement-cmd", "true",
                 "--json", "--repo-root", "/tmp/x"])
    assert code == EXIT_PICKUP_FAILED
    evs = _events(capsys)
    assert evs[-1]["event"] == "hook_failed"
    assert evs[-1]["phase"] == "pickup"


def test_implement_hook_failure_exits_1(monkeypatch, capsys):
    h = _Harness(monkeypatch, [_plan(ready=["M1.1"])])

    def failing_shell(cmd, env, repo_root):
        return 3  # implement-cmd fails

    monkeypatch.setattr(gs, "_run_shell", failing_shell)
    code = _run(["--implement-mode", "hook", "--implement-cmd", "false",
                 "--json", "--repo-root", "/tmp/x"])
    assert code == EXIT_GENERIC
    evs = _events(capsys)
    assert evs[-1]["event"] == "hook_failed"
    assert evs[-1]["phase"] == "implement"
    assert not any(c[0] == "finish-this-task" for c in h.cli_calls)


# ---------------------------------------------------------------------------
# Arg parsing
# ---------------------------------------------------------------------------


def test_hook_mode_requires_implement_cmd():
    from grind_session_args import parse_grind_session_args

    with pytest.raises(SystemExit) as ei:
        parse_grind_session_args(["--implement-mode", "hook", "--repo-root", "/tmp/x"])
    assert ei.value.code == 2


def test_pickup_and_finish_pass_through_flags(monkeypatch, capsys):
    h = _Harness(monkeypatch, [_plan(ready=["M1.1"]), _plan(ready=[])])
    _run(["--implement-mode", "hook", "--implement-cmd", "true",
          "--on-complete", "merge", "--base", "dev", "--remote", "up",
          "--json", "--repo-root", "/tmp/x"])
    pickup = next(c for c in h.cli_calls if c[0] == "do-next-available-task")
    finish = next(c for c in h.cli_calls if c[0] == "finish-this-task")
    assert "--on-complete" in pickup and "merge" in pickup
    assert "--base" in pickup and "dev" in pickup
    assert "--remote" in pickup and "up" in pickup
    assert "--on-complete" in finish and "merge" in finish


# ---------------------------------------------------------------------------
# CLI smoke tests (real subprocess through specy_road.cli)
# ---------------------------------------------------------------------------


def test_cli_grind_session_help() -> None:
    r = subprocess.run(
        [sys.executable, "-m", "specy_road.cli", "grind-session", "--help"],
        cwd=REPO, capture_output=True, text=True, check=True,
    )
    for flag in ("--plan", "--until", "--under", "--max-leaves",
                 "--implement-mode", "--implement-cmd", "--pre-finish-cmd",
                 "--on-complete", "--json"):
        assert flag in r.stdout, flag


def test_cli_grind_session_plan_json() -> None:
    r = subprocess.run(
        [sys.executable, "-m", "specy_road.cli", "grind-session", "--plan",
         "--json", "--repo-root", str(DOGFOOD)],
        cwd=REPO, capture_output=True, text=True, check=True,
    )
    payload = json.loads(r.stdout.strip().splitlines()[0])
    assert payload["event"] == "plan"
    assert "ready" in payload and "waves" in payload and "parallel_batches" in payload
