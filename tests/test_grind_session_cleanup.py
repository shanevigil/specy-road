"""End-of-session behaviour: where the loop leaves you, and what it tidies up.

An unattended merge-mode session used to end on the last feature branch, with
every feature/rm-* it had finished still present locally and on the remote. The
loop now returns to the integration branch, and deletes what it merged only when
asked.
"""

from __future__ import annotations

import json
import os

import pytest

from specy_road.bundled_scripts import grind_session as gs
from specy_road.bundled_scripts import grind_session_events as gse
from specy_road.bundled_scripts.grind_session_events import (
    EXIT_NO_LEAVES,
    EXIT_OK,
    EXIT_PICKUP_FAILED,
)
from tests.test_grind_session import TS, _Harness, _event, _events, _plan, _run

BASE = ["--on-complete", "merge", "--implement-mode", "hook",
        "--implement-cmd", "true", "--json", "--repo-root", "/tmp/x"]

BR1 = "feature/rm-cn-m1-1"
BR2 = "feature/rm-cn-m1-2"


def _one_leaf(monkeypatch, **over) -> _Harness:
    return _Harness(monkeypatch, [_plan(ready=["M1.1"]), _plan(ready=[])], **over)


def _verbs(harness) -> list[str]:
    return [c[0] for c in harness.git_calls]


# ---------------------------------------------------------------------------
# Returning to the integration branch
# ---------------------------------------------------------------------------


def test_merge_mode_checks_out_the_integration_branch_at_the_end(monkeypatch, capsys):
    h = _one_leaf(monkeypatch)

    code = _run([*BASE, "--max-leaves", "1"])

    assert code == EXIT_OK
    assert ["checkout", "main"] in h.git_calls
    event = _event(_events(capsys), "cleanup")
    assert event["checked_out"] is True
    assert event["integration_branch"] == "main"
    assert event["deleted_local"] == []


def test_without_the_flag_it_prints_the_cleanup_command(monkeypatch, capsys):
    _one_leaf(monkeypatch)

    _run([*BASE, "--max-leaves", "1"])

    assert _event(_events(capsys), "cleanup")["hint"] == f"git branch -d {BR1}"


def test_the_hint_covers_the_remote_when_pushing(monkeypatch, capsys):
    _one_leaf(monkeypatch)

    _run([*BASE, "--push", "--max-leaves", "1"])

    hint = _event(_events(capsys), "cleanup")["hint"]
    assert hint == f"git branch -d {BR1} && git push origin --delete {BR1}"


def test_a_checkout_failure_is_non_fatal_and_stops_the_deletes(monkeypatch, capsys):
    h = _one_leaf(monkeypatch)
    h.git_rc["checkout"] = 1

    code = _run([*BASE, "--delete-merged-branches", "--max-leaves", "1"])

    assert code == EXIT_OK
    assert _verbs(h) == ["checkout"]
    event = _event(_events(capsys), "cleanup")
    assert event["checked_out"] is False
    assert event["failed"][0]["step"] == "checkout"


# ---------------------------------------------------------------------------
# Deleting merged branches
# ---------------------------------------------------------------------------


def test_the_flag_deletes_the_branch_locally(monkeypatch, capsys):
    h = _one_leaf(monkeypatch)

    _run([*BASE, "--delete-merged-branches", "--max-leaves", "1"])

    assert ["merge-base", "--is-ancestor", BR1, "main"] in h.git_calls
    assert ["branch", "-d", BR1] in h.git_calls
    assert "push" not in _verbs(h)
    event = _event(_events(capsys), "cleanup")
    assert event["deleted_local"] == [BR1]
    assert event["deleted_remote"] == []
    assert event["hint"] is None


def test_with_push_it_also_deletes_the_remote_branch(monkeypatch, capsys):
    h = _one_leaf(monkeypatch)

    _run([*BASE, "--push", "--delete-merged-branches", "--max-leaves", "1",
          "--base", "dev", "--remote", "up"])

    assert ["push", "up", "--delete", BR1] in h.git_calls
    event = _event(_events(capsys), "cleanup")
    assert event["integration_branch"] == "dev"
    assert event["remote"] == "up"
    assert event["deleted_remote"] == [BR1]


def test_a_branch_the_integration_branch_lacks_is_left_alone(monkeypatch, capsys):
    """auto mode exits 0 on its PR fallback, so 'finished' is not 'merged'."""
    h = _one_leaf(monkeypatch)
    h.git_rc["merge-base"] = 1

    code = _run([*BASE, "--push", "--delete-merged-branches", "--max-leaves", "1"])

    assert code == EXIT_OK
    assert "branch" not in _verbs(h)
    assert "push" not in _verbs(h)
    failure = _event(_events(capsys), "cleanup")["failed"][0]
    assert failure["step"] == "merge_base"
    assert failure["branch"] == BR1


def test_a_failed_local_delete_never_touches_the_remote(monkeypatch, capsys):
    h = _one_leaf(monkeypatch)
    h.git_rc["branch"] = 1

    _run([*BASE, "--push", "--delete-merged-branches", "--max-leaves", "1"])

    assert "push" not in _verbs(h)
    event = _event(_events(capsys), "cleanup")
    assert event["deleted_local"] == []
    assert event["failed"][0]["step"] == "branch_d"


def test_every_branch_the_session_finished_is_collected(monkeypatch, capsys):
    _Harness(monkeypatch, [_plan(ready=["M1.1"]), _plan(ready=["M1.2"]),
                           _plan(ready=[])])

    _run([*BASE, "--delete-merged-branches", "--max-leaves", "2"])

    assert _event(_events(capsys), "cleanup")["deleted_local"] == [BR1, BR2]


# ---------------------------------------------------------------------------
# When cleanup must not run
# ---------------------------------------------------------------------------


def test_no_cleanup_after_a_failed_cycle(monkeypatch, capsys):
    """The dev needs the feature branch exactly as the failure left it."""
    h = _one_leaf(monkeypatch, pickup_rc=1)

    code = _run([*BASE, "--delete-merged-branches"])

    assert code == EXIT_PICKUP_FAILED
    assert h.git_calls == []
    assert [e for e in _events(capsys) if e["event"] == "cleanup"] == []


def test_no_cleanup_when_the_session_finished_nothing(monkeypatch, capsys):
    h = _Harness(monkeypatch, [_plan(ready=[])])

    code = _run([*BASE, "--delete-merged-branches"])

    assert code == EXIT_NO_LEAVES
    assert h.git_calls == []


def test_no_cleanup_in_milestone_subtree_mode(monkeypatch, capsys):
    """finish lands on the rollup branch there, not the integration branch."""
    h = _one_leaf(monkeypatch)

    _run([*BASE, "--milestone-subtree", "--delete-merged-branches", "--max-leaves", "1"])

    assert h.git_calls == []


# ---------------------------------------------------------------------------
# JSONL hygiene
# ---------------------------------------------------------------------------


def test_every_json_event_carries_a_timestamp(monkeypatch, capsys):
    _one_leaf(monkeypatch)

    _run([*BASE, "--max-leaves", "1"])

    evs = _events(capsys)
    assert evs
    for event in evs:
        assert list(event)[:2] == ["event", "ts"]
        assert event["ts"] == TS


def test_the_timestamp_is_utc_to_the_second():
    assert gse._now_iso().endswith("Z")
    assert len(gse._now_iso()) == len("2026-09-06T00:00:00Z")


def test_json_mode_keeps_child_output_off_stdout(monkeypatch, tmp_path, capfd):
    """capfd gives stderr a real file descriptor: the streaming path."""
    monkeypatch.setattr(gs, "CHILD_STDOUT_TO_STDERR", True)

    assert gs._run_shell("echo hello", os.environ.copy(), tmp_path) == 0

    captured = capfd.readouterr()
    assert captured.out == ""
    assert "hello" in captured.err


def test_json_mode_falls_back_when_stderr_has_no_descriptor(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(gs, "CHILD_STDOUT_TO_STDERR", True)

    assert gs._run_shell("echo hello", os.environ.copy(), tmp_path) == 0

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "hello" in captured.err


def test_without_json_the_child_keeps_our_stdout(monkeypatch, tmp_path, capfd):
    monkeypatch.setattr(gs, "CHILD_STDOUT_TO_STDERR", False)

    gs._run_shell("echo hello", os.environ.copy(), tmp_path)

    assert "hello" in capfd.readouterr().out


@pytest.mark.parametrize("json_flag, expected", [(True, True), (False, False)])
def test_the_child_stdout_mode_follows_the_json_flag(monkeypatch, capsys, json_flag, expected):
    _Harness(monkeypatch, [_plan(ready=[])])
    argv = ["--on-complete", "merge", "--implement-mode", "hook",
            "--implement-cmd", "true", "--repo-root", "/tmp/x"]
    if json_flag:
        argv.append("--json")

    _run(argv)

    assert gs.CHILD_STDOUT_TO_STDERR is expected


def test_stdout_stays_parseable_as_jsonl(monkeypatch, capsys):
    _one_leaf(monkeypatch)

    _run([*BASE, "--max-leaves", "1"])

    for line in capsys.readouterr().out.strip().splitlines():
        assert json.loads(line)["event"]
