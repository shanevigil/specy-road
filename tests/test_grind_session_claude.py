"""The grind loop when the implementer is Claude Code.

Kept apart from the loop's own tests: what is under test here is the seam
between the loop and the vendor adapter, not the loop's stop conditions.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from specy_road.bundled_scripts import grind_session as gs
from specy_road.bundled_scripts import grind_session_implement as gsi
from specy_road.bundled_scripts.grind_session_events import EXIT_GENERIC, EXIT_OK
from tests.test_grind_session import _event, _events, _Harness, _plan, _run

def test_a_generic_hook_still_goes_through_the_plain_shell_runner(monkeypatch, capsys):
    """Cursor and other agents keep today's behaviour: one run, rc stops it."""
    h = _Harness(monkeypatch, [_plan(ready=["M1.1"])], implement_rc=1)
    captured: list[str] = []
    monkeypatch.setattr(
        gsi, "_run_capturing", lambda *_a: captured.append("claude path") or (0, "")
    )

    def failing_shell(cmd, env, repo_root):
        h.shell_calls.append(cmd)
        return 1

    monkeypatch.setattr(gs, "_run_shell", failing_shell)

    code = _run(["--on-complete", "merge", "--implement-mode", "hook",
                 "--implement-cmd", "my-agent --prompt x", "--json",
                 "--repo-root", "/tmp/x"])

    assert code == EXIT_GENERIC
    assert captured == []
    assert h.shell_calls == ["my-agent --prompt x"]
    assert _events(capsys)[-1]["event"] == "hook_failed"


def test_a_claude_hook_waits_out_a_limit_and_the_leaf_still_finishes(
    monkeypatch, capsys
):
    h = _Harness(monkeypatch, [_plan(ready=["M1.1"]), _plan(ready=[])])
    limit = (
        "You've hit your Claude Code session limit. Your limit resets "
        f"{(datetime.now(timezone.utc) + timedelta(minutes=30)).strftime('%I:%M%p').lstrip('0').lower()} (UTC).\n"
        "session_id: 3f2c9a7e-15b8-4d21-9c44-77aa10bd3e50\n"
    )
    scripted = [(1, limit), (0, "done")]
    monkeypatch.setattr(gsi, "_run_capturing", lambda *_a: scripted.pop(0))
    monkeypatch.setattr(gsi, "_notify", lambda *_a: None)
    monkeypatch.setattr(gsi.time, "sleep", lambda _s: None)

    code = _run(["--on-complete", "merge", "--implement-mode", "hook",
                 "--implement-cmd", 'claude -p "go"', "--json",
                 "--repo-root", "/tmp/x", "--max-leaves", "1"])

    assert code == EXIT_OK
    evs = _events(capsys)
    limited = _event(evs, "usage_limited")
    assert limited["node_id"] == "M1.1" and limited["attempt"] == 1
    assert _event(evs, "finished")["node_id"] == "M1.1"
    assert scripted == []


def test_an_unrecognized_claude_limit_stops_the_session(monkeypatch, capsys):
    """A wording change must surface, not read as a normal hook failure."""
    _Harness(monkeypatch, [_plan(ready=["M1.1"])])
    monkeypatch.setattr(
        gsi, "_run_capturing", lambda *_a: (1, "API error 429: too many requests.")
    )

    code = _run(["--on-complete", "merge", "--implement-mode", "hook",
                 "--implement-cmd", 'claude -p "go"', "--json",
                 "--repo-root", "/tmp/x"])

    assert code == EXIT_GENERIC
    assert "output format may have changed" in capsys.readouterr().err
