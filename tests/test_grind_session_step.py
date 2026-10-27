"""``grind-session --step pickup|finish``: one phase per run, for an IDE agent."""

from __future__ import annotations

import subprocess
import sys

import pytest

from specy_road.bundled_scripts import grind_session as gs
from specy_road.bundled_scripts import grind_session_in_flight as gsif
from specy_road.bundled_scripts.grind_session_args import parse_grind_session_args
from specy_road.bundled_scripts.grind_session_events import (
    EXIT_BLOCKED,
    EXIT_GENERIC,
    EXIT_NO_LEAVES,
    EXIT_OK,
    EXIT_PICKUP_FAILED,
    EXIT_PRE_FINISH_FAILED,
)
from specy_road.bundled_scripts.session_plan import BlockedLeaf
from tests.test_grind_session import REPO, _Harness, _event, _events, _plan, _run
from tests.test_grind_session_in_flight import _artifacts, _entry, _reg

MERGE = ["--on-complete", "merge", "--json", "--repo-root", "/tmp/x"]


def _verbs(h: _Harness) -> list[str]:
    return [c[0] for c in h.cli_calls]


def _on_claim(monkeypatch, branch="feature/rm-cn", node_id="M1.1"):
    """Check out ``branch`` and make it resolve to ``node_id`` (or nothing)."""
    monkeypatch.setattr(gs, "current_branch", lambda _root: branch)
    monkeypatch.setattr(gs, "_resolve_picked", lambda _r, _b, fallback: node_id or fallback)


def _own_claim(monkeypatch, h: _Harness, *, ready=()):
    """Script a plan in which this clone holds M1.1, plus optional ready leaves."""
    monkeypatch.setattr(gsif, "local_branch_exists", lambda _root, _b: True)
    monkeypatch.setattr(gsif, "checkout_branch", lambda _root, _b: (0, ""))
    monkeypatch.setattr(
        gs, "gather_plan",
        lambda _r, _u: ([{"id": "M1.1", "codename": "cn"}],
                        _reg(_entry("M1.1", "cn")),
                        _plan(ready=list(ready), active=["M1.1"])),
    )


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def test_step_parses_without_an_implement_command():
    assert parse_grind_session_args(["--step", "pickup"]).step == "pickup"
    assert parse_grind_session_args(["--step", "finish"]).step == "finish"


@pytest.mark.parametrize("extra", [
    ["--implement-cmd", "true"],
    ["--implement-mode", "hook"],
    ["--plan"],
    ["--delete-merged-branches"],
])
def test_step_rejects_flags_it_would_silently_ignore(extra, capsys):
    with pytest.raises(SystemExit) as ei:
        parse_grind_session_args(["--step", "pickup", *extra])
    assert ei.value.code == 2
    assert "--step cannot be combined" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# --step pickup
# ---------------------------------------------------------------------------


def test_pickup_claims_one_leaf_and_stops_before_implementing(monkeypatch, capsys):
    h = _Harness(monkeypatch, [_plan(ready=["M1.1", "M1.2"])])
    assert _run(["--step", "pickup", *MERGE]) == EXIT_OK
    assert _verbs(h) == ["do-next-available-task"]
    assert h.shell_calls == [] and h.git_calls == []
    evs = _events(capsys)
    assert [e["event"] for e in evs] == ["picked"]
    assert evs[0]["node_id"] == "M1.1"
    assert evs[0]["prompt"] == "work/prompt-M1.1.md"
    assert evs[0]["brief"] == "work/brief-M1.1.md"


def test_pickup_failure_exits_5(monkeypatch, capsys):
    _Harness(monkeypatch, [_plan(ready=["M1.1"])], pickup_rc=9)
    assert _run(["--step", "pickup", *MERGE]) == EXIT_PICKUP_FAILED
    ev = _event(_events(capsys), "hook_failed")
    assert (ev["phase"], ev["rc"]) == ("pickup", 9)


def test_pickup_resumes_an_own_claim_without_the_flag(monkeypatch, capsys, tmp_path):
    _artifacts(tmp_path, "M1.1")
    h = _Harness(monkeypatch, [_plan()])
    _own_claim(monkeypatch, h)
    code = _run(["--step", "pickup", "--on-complete", "merge", "--json",
                 "--repo-root", str(tmp_path)])
    assert code == EXIT_OK
    assert h.cli_calls == []
    ev = _event(_events(capsys), "resumed")
    assert (ev["node_id"], ev["branch"]) == ("M1.1", "feature/rm-cn")


def test_an_own_claim_wins_over_a_ready_leaf(monkeypatch, capsys, tmp_path):
    """A second claim on top of an unfinished one is what finish cannot untangle."""
    _artifacts(tmp_path, "M1.1")
    h = _Harness(monkeypatch, [_plan()])
    _own_claim(monkeypatch, h, ready=["M1.2"])
    code = _run(["--step", "pickup", "--on-complete", "merge", "--json",
                 "--repo-root", str(tmp_path)])
    assert code == EXIT_OK
    assert "do-next-available-task" not in _verbs(h)
    assert [e["event"] for e in _events(capsys)] == ["resumed"]


def test_pickup_reports_a_failed_resume(monkeypatch, capsys, tmp_path):
    h = _Harness(monkeypatch, [_plan()])
    _own_claim(monkeypatch, h)
    monkeypatch.setattr(gsif, "checkout_branch", lambda _r, _b: (1, "dirty tree"))
    code = _run(["--step", "pickup", "--on-complete", "merge", "--json",
                 "--repo-root", str(tmp_path)])
    assert code == EXIT_GENERIC
    assert _event(_events(capsys), "hook_failed")["phase"] == "resume"


def test_pickup_with_only_blocked_work_exits_3(monkeypatch, capsys):
    blocked = BlockedLeaf(node_id="M2.1", codename="x", waiting_on=["M1.9"],
                          reason="dependency")
    h = _Harness(monkeypatch, [_plan(blocked=[blocked])])
    assert _run(["--step", "pickup", *MERGE]) == EXIT_BLOCKED
    assert h.cli_calls == []


def test_pickup_with_nothing_to_do_exits_2(monkeypatch, capsys):
    h = _Harness(monkeypatch, [_plan()])
    assert _run(["--step", "pickup", *MERGE]) == EXIT_NO_LEAVES
    assert h.cli_calls == []


def test_pickup_refuses_pr_mode(monkeypatch, capsys):
    h = _Harness(monkeypatch, [_plan(ready=["M1.1"])])
    code = _run(["--step", "pickup", "--json", "--repo-root", "/tmp/x"])
    assert code == EXIT_GENERIC
    assert h.cli_calls == []
    assert "'pr' mode" in capsys.readouterr().err


def test_pickup_passes_scope_and_mode_through(monkeypatch, capsys):
    h = _Harness(monkeypatch, [_plan(ready=["M1.1"])])
    _run(["--step", "pickup", "--under", "M1", "--base", "dev", *MERGE])
    pickup = h.cli_calls[0]
    assert pickup[pickup.index("--under") + 1] == "M1"
    assert pickup[pickup.index("--base") + 1] == "dev"
    assert pickup[pickup.index("--on-complete") + 1] == "merge"


# ---------------------------------------------------------------------------
# --step finish
# ---------------------------------------------------------------------------


def test_finish_runs_pre_finish_then_finish(monkeypatch, capsys):
    h = _Harness(monkeypatch, [_plan()])
    _on_claim(monkeypatch)
    code = _run(["--step", "finish", "--pre-finish-cmd", "make test",
                 "--push", *MERGE])
    assert code == EXIT_OK
    assert h.shell_calls == ["make test"]
    assert _verbs(h) == ["finish-this-task"]
    finish = h.cli_calls[0]
    assert "--push" in finish and finish[finish.index("--on-complete") + 1] == "merge"
    assert [e["event"] for e in _events(capsys)] == ["pre_finish", "finished"]


def test_finish_reports_until_reached(monkeypatch, capsys):
    _Harness(monkeypatch, [_plan()])
    _on_claim(monkeypatch)
    assert _run(["--step", "finish", "--until", "M1.1", *MERGE]) == EXIT_OK
    ev = _event(_events(capsys), "stopped")
    assert (ev["reason"], ev["node_id"]) == ("until_reached", "M1.1")


def test_finish_without_until_match_does_not_stop(monkeypatch, capsys):
    _Harness(monkeypatch, [_plan()])
    _on_claim(monkeypatch)
    assert _run(["--step", "finish", "--until", "M9.9", *MERGE]) == EXIT_OK
    assert "stopped" not in [e["event"] for e in _events(capsys)]


def test_finish_pre_finish_failure_exits_4(monkeypatch, capsys):
    h = _Harness(monkeypatch, [_plan()])
    _on_claim(monkeypatch)
    monkeypatch.setattr(gs, "_run_shell", lambda *_a: 3)
    code = _run(["--step", "finish", "--pre-finish-cmd", "make test", *MERGE])
    assert code == EXIT_PRE_FINISH_FAILED
    assert h.cli_calls == []


def test_finish_failure_exits_1(monkeypatch, capsys):
    """Includes an open review gate: finish-this-task explains and exits 1."""
    _Harness(monkeypatch, [_plan()], finish_rc=1)
    _on_claim(monkeypatch)
    assert _run(["--step", "finish", *MERGE]) == EXIT_GENERIC
    assert _event(_events(capsys), "hook_failed")["phase"] == "finish"


@pytest.mark.parametrize("branch,node_id", [
    ("dev", "M1.1"),                 # not a feature branch at all
    ("feature/rm-stranger", ""),     # no registry row for that codename
    ("", ""),                        # detached HEAD
])
def test_finish_refuses_a_branch_that_is_not_a_claim(monkeypatch, capsys, branch, node_id):
    h = _Harness(monkeypatch, [_plan()])
    _on_claim(monkeypatch, branch=branch, node_id=node_id)
    code = _run(["--step", "finish", "--pre-finish-cmd", "make test", *MERGE])
    assert code == EXIT_GENERIC
    assert h.cli_calls == [] and h.shell_calls == []
    captured = capsys.readouterr()
    assert "--step pickup" in captured.err
    assert '"phase": "locate_claim"' in captured.out


def test_finish_refuses_pr_mode(monkeypatch, capsys):
    h = _Harness(monkeypatch, [_plan()])
    _on_claim(monkeypatch)
    assert _run(["--step", "finish", "--json", "--repo-root", "/tmp/x"]) == EXIT_GENERIC
    assert h.cli_calls == []


def test_json_step_routes_child_output_to_stderr_on_its_own(monkeypatch, capsys):
    """The CLI runs grind_session as ``__main__``; run_session's flag is on that copy.

    The step module's ``gs`` is the imported copy, so run_step must set the
    flag itself or the pickup banner corrupts the JSONL on stdout.
    """
    from specy_road.bundled_scripts.grind_session_events import EventEmitter
    from specy_road.bundled_scripts.grind_session_step import run_step

    _Harness(monkeypatch, [_plan(ready=["M1.1"])])
    assert gs.CHILD_STDOUT_TO_STDERR is False
    args = parse_grind_session_args(["--step", "pickup", *MERGE])
    assert run_step(args, args.repo_root, EventEmitter(as_json=True)) == EXIT_OK
    assert gs.CHILD_STDOUT_TO_STDERR is True


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_cli_help_lists_step() -> None:
    r = subprocess.run(
        [sys.executable, "-m", "specy_road.cli", "grind-session", "--help"],
        cwd=REPO, capture_output=True, text=True, check=True,
    )
    assert "--step {pickup,finish}" in r.stdout
