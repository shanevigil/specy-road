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

from specy_road.orchestration.grind import grind_session as gs
from specy_road.orchestration.grind import grind_session_cleanup as gsc
from specy_road import merged_branch
from specy_road.orchestration.grind.grind_session_events import (
    EXIT_NO_LEAVES,
    EXIT_OK,
    EXIT_PICKUP_FAILED,
)
from tests.support.same.events_bc2d3e84325c import events
from tests.support.same.plan_a42dad7814e8 import plan
from tests.support.extracted.grind_session import TS, Harness, event as event_fn, run

BASE = ["--on-complete", "merge", "--implement-mode", "hook",
        "--implement-cmd", "true", "--json", "--repo-root", "/tmp/x"]

BR1 = "feature/rm-cn-m1-1"
BR2 = "feature/rm-cn-m1-2"


def _one_leaf(monkeypatch, **over) -> Harness:
    return Harness(monkeypatch, [plan(ready=["M1.1"]), plan(ready=[])], **over)


def _verbs(harness) -> list[str]:
    return [c[0] for c in harness.git_calls]


# ---------------------------------------------------------------------------
# Returning to the integration branch
# ---------------------------------------------------------------------------


def test_merge_mode_checks_out_the_integration_branch_at_the_end(monkeypatch, capsys):
    h = _one_leaf(monkeypatch)

    code = run([*BASE, "--max-leaves", "1"])

    assert code == EXIT_OK
    assert ["checkout", "main"] in h.git_calls
    event = event_fn(events(capsys), "cleanup")
    assert event["checked_out"] is True
    assert event["integration_branch"] == "main"
    assert event["deleted_local"] == []


def test_without_the_flag_it_prints_the_cleanup_command(monkeypatch, capsys):
    _one_leaf(monkeypatch)

    run([*BASE, "--max-leaves", "1"])

    assert event_fn(events(capsys), "cleanup")["hint"] == f"git branch -d {BR1}"


def test_the_hint_covers_the_remote_when_pushing(monkeypatch, capsys):
    _one_leaf(monkeypatch)

    run([*BASE, "--push", "--max-leaves", "1"])

    hint = event_fn(events(capsys), "cleanup")["hint"]
    assert hint == f"git branch -d {BR1} && git push origin --delete {BR1}"


def test_a_checkout_failure_is_non_fatal_and_stops_the_deletes(monkeypatch, capsys):
    h = _one_leaf(monkeypatch)
    h.git_rc["checkout"] = 1

    code = run([*BASE, "--delete-merged-branches", "--max-leaves", "1"])

    assert code == EXIT_OK
    assert _verbs(h) == ["checkout"]
    event = event_fn(events(capsys), "cleanup")
    assert event["checked_out"] is False
    assert event["failed"][0]["step"] == "checkout"


# ---------------------------------------------------------------------------
# Deleting merged branches
# ---------------------------------------------------------------------------


def test_the_flag_deletes_the_branch_locally(monkeypatch, capsys):
    h = _one_leaf(monkeypatch)

    run([*BASE, "--delete-merged-branches", "--max-leaves", "1"])

    assert ["merge-base", "--is-ancestor", BR1, "main"] in h.git_calls
    assert ["branch", "-d", BR1] in h.git_calls
    assert "push" not in _verbs(h)
    event = event_fn(events(capsys), "cleanup")
    assert event["deleted_local"] == [BR1]
    assert event["deleted_remote"] == []
    assert event["hint"] is None


def test_with_push_it_also_deletes_the_remote_branch(monkeypatch, capsys):
    h = _one_leaf(monkeypatch)

    run([*BASE, "--push", "--delete-merged-branches", "--max-leaves", "1",
          "--base", "dev", "--remote", "up"])

    assert ["push", "up", f"--force-with-lease=refs/heads/{BR1}:{'a' * 40}", "--delete", BR1] in h.git_calls
    event = event_fn(events(capsys), "cleanup")
    assert event["integration_branch"] == "dev"
    assert event["remote"] == "up"
    assert event["deleted_remote"] == [BR1]


def test_a_branch_the_integration_branch_lacks_is_left_alone(monkeypatch, capsys):
    """auto mode exits 0 on its PR fallback, so 'finished' is not 'merged'."""
    h = _one_leaf(monkeypatch)
    h.git_rc["merge-base"] = 1

    code = run([*BASE, "--push", "--delete-merged-branches", "--max-leaves", "1"])

    assert code == EXIT_OK
    assert "branch" not in _verbs(h)
    assert "push" not in _verbs(h)
    failure = event_fn(events(capsys), "cleanup")["failed"][0]
    assert failure["step"] == "merge_base"
    assert failure["branch"] == BR1


def test_a_failed_local_delete_never_touches_the_remote(monkeypatch, capsys):
    h = _one_leaf(monkeypatch)
    h.git_rc["branch"] = 1

    run([*BASE, "--push", "--delete-merged-branches", "--max-leaves", "1"])

    assert "push" not in _verbs(h)
    event = event_fn(events(capsys), "cleanup")
    assert event["deleted_local"] == []
    assert event["failed"][0]["step"] == "branch_d"


def test_every_branch_the_session_finished_is_collected(monkeypatch, capsys):
    Harness(monkeypatch, [plan(ready=["M1.1"]), plan(ready=["M1.2"]),
                           plan(ready=[])])

    run([*BASE, "--delete-merged-branches", "--max-leaves", "2"])

    assert event_fn(events(capsys), "cleanup")["deleted_local"] == [BR1, BR2]


# ---------------------------------------------------------------------------
# When cleanup must not run
# ---------------------------------------------------------------------------


def test_no_cleanup_after_a_failed_cycle(monkeypatch, capsys):
    """The dev needs the feature branch exactly as the failure left it."""
    h = _one_leaf(monkeypatch, pickup_rc=1)

    code = run([*BASE, "--delete-merged-branches"])

    assert code == EXIT_PICKUP_FAILED
    assert h.git_calls == []
    assert [e for e in events(capsys) if e["event"] == "cleanup"] == []


def test_no_cleanup_when_the_session_finished_nothing(monkeypatch, capsys):
    h = Harness(monkeypatch, [plan(ready=[])])

    code = run([*BASE, "--delete-merged-branches"])

    assert code == EXIT_NO_LEAVES
    assert h.git_calls == []


def test_no_cleanup_in_milestone_subtree_mode(monkeypatch, capsys):
    """finish lands on the rollup branch there, not the integration branch."""
    h = _one_leaf(monkeypatch)

    run([*BASE, "--milestone-subtree", "--delete-merged-branches", "--max-leaves", "1"])

    assert h.git_calls == []


# ---------------------------------------------------------------------------
# JSONL hygiene
# ---------------------------------------------------------------------------


def test_every_json_event_carries_a_timestamp(monkeypatch, capsys):
    _one_leaf(monkeypatch)

    run([*BASE, "--max-leaves", "1"])

    evs = events(capsys)
    assert evs
    for event in evs:
        assert list(event)[:2] == ["event", "ts"]
        assert event["ts"] == TS


def test_json_mode_keeps_child_output_off_stdout(monkeypatch, tmp_path, capfd):
    """capfd gives stderr a real file descriptor: the streaming path."""
    monkeypatch.setattr(gs, "CHILD_STDOUT_TO_STDERR", True)

    assert gs.run_shell("echo hello", os.environ.copy(), tmp_path) == 0

    captured = capfd.readouterr()
    assert captured.out == ""
    assert "hello" in captured.err


def test_json_mode_falls_back_when_stderr_has_no_descriptor(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(gs, "CHILD_STDOUT_TO_STDERR", True)

    assert gs.run_shell("echo hello", os.environ.copy(), tmp_path) == 0

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "hello" in captured.err


def test_without_json_the_child_keeps_our_stdout(monkeypatch, tmp_path, capfd):
    monkeypatch.setattr(gs, "CHILD_STDOUT_TO_STDERR", False)

    gs.run_shell("echo hello", os.environ.copy(), tmp_path)

    assert "hello" in capfd.readouterr().out


@pytest.mark.parametrize("json_flag, expected", [(True, True), (False, False)])
def test_the_child_stdout_mode_follows_the_json_flag(monkeypatch, capsys, json_flag, expected):
    Harness(monkeypatch, [plan(ready=[])])
    argv = ["--on-complete", "merge", "--implement-mode", "hook",
            "--implement-cmd", "true", "--repo-root", "/tmp/x"]
    if json_flag:
        argv.append("--json")

    run(argv)

    assert gs.CHILD_STDOUT_TO_STDERR is expected


def test_stdout_stays_parseable_as_jsonl(monkeypatch, capsys):
    _one_leaf(monkeypatch)

    run([*BASE, "--max-leaves", "1"])

    for line in capsys.readouterr().out.strip().splitlines():
        assert json.loads(line)["event"]


def test_a_rejected_remote_delete_keeps_the_local_one_and_warns(monkeypatch, capsys):
    """Branch protection on the remote must not undo or hide the local delete."""
    h = _one_leaf(monkeypatch)
    h.git_rc["push"] = 1

    code = run([*BASE, "--push", "--delete-merged-branches", "--max-leaves", "1"])

    assert code == EXIT_OK
    event = event_fn(events(capsys), "cleanup")
    assert event["deleted_local"] == [BR1]
    assert event["deleted_remote"] == []
    assert event["failed"][0]["step"] == "push_delete"


def test_the_remote_branch_must_also_be_contained_in_the_integration_branch(
    monkeypatch, capsys
):
    """Someone else's commit on the same branch must not vanish with our delete."""
    h = _one_leaf(monkeypatch)

    def fake_git(git_args, repo_root):
        h.git_calls.append(list(git_args))
        # The local branch is merged; the remote-tracking ref is not.
        if git_args[0] == "merge-base" and git_args[2].startswith("origin/"):
            return 1, ""
        return 0, ""

    monkeypatch.setattr(gsc, "git_code", fake_git)
    monkeypatch.setattr(merged_branch, "git_code", fake_git)

    run([*BASE, "--push", "--delete-merged-branches", "--max-leaves", "1"])

    assert ["merge-base", "--is-ancestor", f"origin/{BR1}", "main"] in h.git_calls
    assert "push" not in _verbs(h)
    event = event_fn(events(capsys), "cleanup")
    assert event["deleted_local"] == [BR1]
    assert event["deleted_remote"] == []
    assert "not contained in main" in event["failed"][0]["message"]


def test_the_human_summary_names_the_branch_and_the_cleanup_command(
    monkeypatch, capsys
):
    """Without --json this line is the only report the session gives."""
    _one_leaf(monkeypatch)

    run(["--on-complete", "merge", "--implement-mode", "hook", "--implement-cmd",
          "true", "--repo-root", "/tmp/x", "--max-leaves", "1"])

    out = capsys.readouterr().out
    assert "cleanup: on main" in out
    assert "deleted 0 local / 0 remote" in out
    assert f"git branch -d {BR1}" in out


def test_the_human_summary_reports_a_failed_checkout(monkeypatch, capsys):
    h = _one_leaf(monkeypatch)
    h.git_rc["checkout"] = 1

    run(["--on-complete", "merge", "--implement-mode", "hook", "--implement-cmd",
          "true", "--repo-root", "/tmp/x", "--max-leaves", "1"])

    out = capsys.readouterr().out
    assert "could NOT return to main" in out
    assert "warning: checkout main" in out
