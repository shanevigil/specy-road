"""Tests for the grind-session loop orchestrator (``grind_session``)."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

from specy_road.orchestration.grind import grind_session as gs
from specy_road.orchestration.grind import grind_session_cleanup as gsc
from specy_road import merged_branch
from specy_road.orchestration.grind import grind_session_events as gse
from tests.support.same.events_bc2d3e84325c import events
from tests.support.same.plan_a42dad7814e8 import plan as plan_fn
from tests.support.extracted.grind_session import REPO, TS, Harness, event, node, run

DOGFOOD = REPO / "tests" / "fixtures" / "specy_road_dogfood"
from specy_road.orchestration.grind.grind_session_events import (
    EXIT_BLOCKED,
    EXIT_GENERIC,
    EXIT_NO_LEAVES,
    EXIT_OK,
    EXIT_PICKUP_FAILED,
    EXIT_PRE_FINISH_FAILED,
)
from specy_road.orchestration.grind.session_plan import BlockedLeaf, SessionPlan, Wave
















# ---------------------------------------------------------------------------
# Plan mode
# ---------------------------------------------------------------------------


def test_plan_mode_emits_plan_and_no_git(monkeypatch, capsys):
    h = Harness(monkeypatch, [plan_fn(ready=["M1.1"], blocked=[
        BlockedLeaf("M1.2", "cn", ["M1.1"], "dependency")])])
    code = run(["--plan", "--json", "--repo-root", "/tmp/x"])
    assert code == EXIT_OK
    evs = events(capsys)
    assert evs[0]["event"] == "plan"
    assert evs[0]["ready"] == ["M1.1"]
    assert h.cli_calls == []  # no pickup/finish in plan mode


# ---------------------------------------------------------------------------
# Loop happy paths
# ---------------------------------------------------------------------------


def test_loop_hook_mode_max_leaves(monkeypatch, capsys):
    plans = [plan_fn(ready=["M1.1"]), plan_fn(ready=["M1.2"]), plan_fn(ready=["M1.3"])]
    h = Harness(monkeypatch, plans)
    code = run(["--on-complete", "merge", "--implement-mode", "hook", "--implement-cmd", "true",
                 "--max-leaves", "2", "--json", "--repo-root", "/tmp/x"])
    assert code == EXIT_OK
    evs = events(capsys)
    finished = [e for e in evs if e["event"] == "finished"]
    assert [e["node_id"] for e in finished] == ["M1.1", "M1.2"]
    assert event(evs, "stopped") == {
        "event": "stopped", "ts": TS, "reason": "max_leaves", "node_id": "M1.2",
    }
    pickups = [c for c in h.cli_calls if c[0] == "do-next-available-task"]
    assert len(pickups) == 2


def test_loop_until_stops_after_node(monkeypatch, capsys):
    plans = [plan_fn(ready=["M1.1"]), plan_fn(ready=["M1.2"]), plan_fn(ready=["M1.3"])]
    Harness(monkeypatch, plans)
    code = run(["--on-complete", "merge", "--implement-mode", "hook", "--implement-cmd", "true",
                 "--until", "M1.2", "--json", "--repo-root", "/tmp/x"])
    assert code == EXIT_OK
    evs = events(capsys)
    assert event(evs, "stopped") == {
        "event": "stopped", "ts": TS, "reason": "until_reached", "node_id": "M1.2",
    }


def test_loop_runs_until_no_work(monkeypatch, capsys):
    plans = [plan_fn(ready=["M1.1"]), plan_fn(ready=[])]
    Harness(monkeypatch, plans)
    code = run(["--on-complete", "merge", "--implement-mode", "hook", "--implement-cmd", "true",
                 "--json", "--repo-root", "/tmp/x"])
    assert code == EXIT_OK
    evs = events(capsys)
    assert event(evs, "stopped")["reason"] == "no_work"


# ---------------------------------------------------------------------------
# Stop / failure exit codes
# ---------------------------------------------------------------------------


def test_blocked_only_exits_3(monkeypatch, capsys):
    plan = plan_fn(ready=[], blocked=[BlockedLeaf("M11.1", "cn", ["M10.5"], "dependency")])
    h = Harness(monkeypatch, [plan])
    code = run(["--on-complete", "merge", "--implement-mode", "hook", "--implement-cmd", "true",
                 "--json", "--repo-root", "/tmp/x"])
    assert code == EXIT_BLOCKED
    evs = events(capsys)
    assert evs[-1]["event"] == "blocked"
    assert evs[-1]["waiting_on"] == ["M10.5"]
    assert h.cli_calls == []  # never attempted pickup


def test_no_actionable_leaves_exits_2(monkeypatch, capsys):
    Harness(monkeypatch, [plan_fn(ready=[])])
    code = run(["--on-complete", "merge", "--implement-mode", "hook", "--implement-cmd", "true",
                 "--json", "--repo-root", "/tmp/x"])
    assert code == EXIT_NO_LEAVES


def test_pre_finish_failure_exits_4_and_skips_finish(monkeypatch, capsys):
    h = Harness(monkeypatch, [plan_fn(ready=["M1.1"])])

    def failing_shell(cmd, env, repo_root):
        h.shell_calls.append(cmd)
        return 2 if cmd == "make test" else 0  # only the pre-finish hook fails

    monkeypatch.setattr(gs, "_run_shell", failing_shell)
    code = run(["--on-complete", "merge", "--implement-mode", "hook", "--implement-cmd", "true",
                 "--pre-finish-cmd", "make test", "--json", "--repo-root", "/tmp/x"])
    assert code == EXIT_PRE_FINISH_FAILED
    # finish-this-task must NOT have been called.
    assert not any(c[0] == "finish-this-task" for c in h.cli_calls)
    evs = events(capsys)
    assert evs[-1]["event"] == "hook_failed"
    assert evs[-1]["phase"] == "pre_finish"


def test_pickup_failure_exits_5(monkeypatch, capsys):
    h = Harness(monkeypatch, [plan_fn(ready=["M1.1"])], pickup_rc=1)
    code = run(["--on-complete", "merge", "--implement-mode", "hook", "--implement-cmd", "true",
                 "--json", "--repo-root", "/tmp/x"])
    assert code == EXIT_PICKUP_FAILED
    evs = events(capsys)
    assert evs[-1]["event"] == "hook_failed"
    assert evs[-1]["phase"] == "pickup"


def test_implement_hook_failure_exits_1(monkeypatch, capsys):
    h = Harness(monkeypatch, [plan_fn(ready=["M1.1"])])

    def failing_shell(cmd, env, repo_root):
        return 3  # implement-cmd fails

    monkeypatch.setattr(gs, "_run_shell", failing_shell)
    code = run(["--on-complete", "merge", "--implement-mode", "hook", "--implement-cmd", "false",
                 "--json", "--repo-root", "/tmp/x"])
    assert code == EXIT_GENERIC
    evs = events(capsys)
    assert evs[-1]["event"] == "hook_failed"
    assert evs[-1]["phase"] == "implement"
    assert not any(c[0] == "finish-this-task" for c in h.cli_calls)


# ---------------------------------------------------------------------------
# Arg parsing
# ---------------------------------------------------------------------------


def test_hook_mode_requires_implement_cmd():
    from specy_road.bundled_scripts.grind_session_args import parse_grind_session_args

    with pytest.raises(SystemExit) as ei:
        parse_grind_session_args(["--implement-mode", "hook", "--repo-root", "/tmp/x"])
    assert ei.value.code == 2


def test_pickup_and_finish_pass_through_flags(monkeypatch, capsys):
    h = Harness(monkeypatch, [plan_fn(ready=["M1.1"]), plan_fn(ready=[])])
    run(["--implement-mode", "hook", "--implement-cmd", "true",
          "--on-complete", "merge", "--base", "dev", "--remote", "up",
          "--json", "--repo-root", "/tmp/x"])
    pickup = next(c for c in h.cli_calls if c[0] == "do-next-available-task")
    finish = next(c for c in h.cli_calls if c[0] == "finish-this-task")
    assert "--on-complete" in pickup and "merge" in pickup
    assert "--base" in pickup and "dev" in pickup
    assert "--remote" in pickup and "up" in pickup
    assert "--on-complete" in finish and "merge" in finish


# ---------------------------------------------------------------------------
# on_complete guard
# ---------------------------------------------------------------------------


def test_loop_refuses_implicit_pr_mode(monkeypatch, capsys):
    """`pr` is the fallback when nothing declares a mode, and it never merges.

    Without this guard an unattended grind in a repo whose git-workflow.yaml
    omits `on_complete` opens a PR per leaf and strands every finish on its
    feature branch, where the next pickup cannot see it.
    """
    h = Harness(monkeypatch, [plan_fn(ready=["M1.1"])])
    code = run(["--implement-mode", "hook", "--implement-cmd", "true",
                 "--json", "--repo-root", "/tmp/x"])
    assert code == EXIT_GENERIC
    assert h.cli_calls == []  # refused before any pickup
    assert "'pr' mode" in capsys.readouterr().err


def test_loop_refuses_explicit_pr_mode(monkeypatch, capsys):
    h = Harness(monkeypatch, [plan_fn(ready=["M1.1"])])
    code = run(["--on-complete", "pr", "--implement-mode", "hook",
                 "--implement-cmd", "true", "--json", "--repo-root", "/tmp/x"])
    assert code == EXIT_GENERIC
    assert h.cli_calls == []


def test_plan_mode_is_allowed_in_pr_mode(monkeypatch, capsys):
    """--plan is read-only, so the merge requirement does not apply."""
    Harness(monkeypatch, [plan_fn(ready=["M1.1"])])
    assert run(["--plan", "--json", "--repo-root", "/tmp/x"]) == EXIT_OK


def test_git_workflow_on_complete_satisfies_the_guard(monkeypatch, capsys, tmp_path):
    """An explicit mode in git-workflow.yaml means no flag is needed."""
    (tmp_path / "roadmap").mkdir()
    (tmp_path / "roadmap" / "git-workflow.yaml").write_text(
        "version: 1\nintegration_branch: main\nremote: origin\non_complete: merge\n",
        encoding="utf-8",
    )
    Harness(monkeypatch, [plan_fn(ready=["M1.1"]), plan_fn(ready=[])])
    code = run(["--implement-mode", "hook", "--implement-cmd", "true",
                 "--json", "--repo-root", str(tmp_path)])
    assert code == EXIT_OK


def test_resolved_mode_is_forwarded_to_every_cycle(monkeypatch, capsys, tmp_path):
    """Pinning the mode is what stops the pickup prompt reintroducing `pr`.

    Without an explicit --on-complete, each cycle's do-next-available-task
    prompts on a TTY and writes the answer to the session file, which
    finish-this-task prefers over git-workflow.yaml.
    """
    (tmp_path / "roadmap").mkdir()
    (tmp_path / "roadmap" / "git-workflow.yaml").write_text(
        "version: 1\nintegration_branch: main\nremote: origin\non_complete: merge\n",
        encoding="utf-8",
    )
    h = Harness(monkeypatch, [plan_fn(ready=["M1.1"]), plan_fn(ready=[])])
    run(["--implement-mode", "hook", "--implement-cmd", "true",
          "--json", "--repo-root", str(tmp_path)])
    pickup = next(c for c in h.cli_calls if c[0] == "do-next-available-task")
    finish = next(c for c in h.cli_calls if c[0] == "finish-this-task")
    assert pickup[pickup.index("--on-complete") + 1] == "merge"
    assert finish[finish.index("--on-complete") + 1] == "merge"


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
                 "--on-complete", "--json", "--max-limit-waits",
                 "--max-limit-wait-hours", "--limit-wait-grace-seconds",
                 "--max-empty-retries"):
        assert flag in r.stdout, flag


def test_cli_grind_session_rejects_negative_limit_flags() -> None:
    r = subprocess.run(
        [sys.executable, "-m", "specy_road.cli", "grind-session",
         "--max-limit-wait-hours", "-1", "--repo-root", str(DOGFOOD)],
        cwd=REPO, capture_output=True, text=True,
    )
    assert r.returncode == 2
    assert "--max-limit-wait-hours must not be negative" in r.stderr


def test_cli_grind_session_plan_json() -> None:
    r = subprocess.run(
        [sys.executable, "-m", "specy_road.cli", "grind-session", "--plan",
         "--json", "--repo-root", str(DOGFOOD)],
        cwd=REPO, capture_output=True, text=True, check=True,
    )
    payload = json.loads(r.stdout.strip().splitlines()[0])
    assert payload["event"] == "plan"
    assert "ready" in payload and "waves" in payload and "parallel_batches" in payload

