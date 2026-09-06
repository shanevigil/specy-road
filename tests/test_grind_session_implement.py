"""The implement step around a Claude usage limit.

Generic hooks must behave exactly as before; only a Claude CLI hook is waited
out, and only for a limit that states when it lifts. No live Claude, no reading
the real ~/.claude — everything is injected.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from specy_road.bundled_scripts import grind_session_implement as gsi

NOW = datetime(2026, 9, 6, 20, 0, tzinfo=timezone.utc)
CLAUDE = 'claude -p --permission-mode acceptEdits "do the task"'
SESSION = "3f2c9a7e-15b8-4d21-9c44-77aa10bd3e50"


def _limit_text(*, minutes_ahead: int = 40, session: str | None = SESSION) -> str:
    """A timed-limit message whose reset really is that far from now."""
    reset = datetime.now(timezone.utc) + timedelta(minutes=minutes_ahead)
    stamp = reset.strftime("%I:%M%p").lstrip("0").lower()
    text = (
        "You've hit your Claude Code session limit. "
        f"Your limit resets {stamp} (UTC).\n"
    )
    return text + (f"session_id: {session}\n" if session else "")


LIMIT = _limit_text()


class _Emitter:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def emit(self, event: str, **fields) -> None:
        self.events.append((event, fields))


def _runs(monkeypatch, results):
    """Script `_run_capturing` with (rc, output) pairs; record the commands."""
    seen: list[str] = []
    queue = list(results)

    def fake(cmd, env, repo_root):
        seen.append(cmd)
        return queue.pop(0) if queue else (0, "")

    monkeypatch.setattr(gsi, "_run_capturing", fake)
    monkeypatch.setattr(gsi, "_notify", lambda *_a: None)
    return seen


@pytest.fixture(autouse=True)
def _empty_claude_home(tmp_path_factory, monkeypatch):
    """Never consult the developer's real ~/.claude during a test.

    Redirects HOME rather than stubbing the lookup, so the lookup itself stays
    under test and simply finds nothing.
    """
    empty = tmp_path_factory.mktemp("home")
    monkeypatch.setattr(gsi.Path, "home", classmethod(lambda _cls: empty))


# ---------------------------------------------------------------------------
# Sniffing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "cmd, expected",
    [
        ('claude -p "x"', True),
        ("/opt/homebrew/bin/claude -p x", True),
        ("  claude --resume abc -p x", True),
        ("my-agent --prompt x", False),
        ("claude-wrapper x", False),
        ("cursor-agent run", False),
        ("", False),
        ('unbalanced "quote', False),
    ],
)
def test_only_the_claude_cli_takes_the_claude_path(cmd, expected) -> None:
    assert gsi.is_claude_cli(cmd) is expected


def test_a_generic_hook_runs_exactly_once_through_the_old_runner(monkeypatch) -> None:
    calls: list[tuple] = []

    def run_shell(cmd, env, repo_root):
        calls.append((cmd, repo_root))
        return 1

    monkeypatch.setattr(gsi, "_run_capturing", lambda *_a: pytest.fail("captured"))

    rc = gsi.run_implement_hook(
        "my-agent --prompt x", {}, Path("/repo"), run_shell=run_shell
    )

    assert rc == 1
    assert calls == [("my-agent --prompt x", Path("/repo"))]


# ---------------------------------------------------------------------------
# Waiting out a timed limit
# ---------------------------------------------------------------------------


def test_a_timed_limit_is_waited_out_and_the_session_resumed(monkeypatch) -> None:
    seen = _runs(monkeypatch, [(1, LIMIT), (0, "done")])
    slept: list[float] = []
    emitter = _Emitter()

    rc = gsi.run_implement_hook(
        CLAUDE, {}, Path("/repo"), emitter=emitter, node_id="M1.1",
        run_shell=lambda *_a: pytest.fail("generic path"), sleep=slept.append,
    )

    assert rc == 0
    assert len(seen) == 2
    assert seen[0] == CLAUDE
    assert "--resume 3f2c9a7e-15b8-4d21-9c44-77aa10bd3e50" in seen[1]
    # The user's own flags survive; nothing dangerous is added.
    assert "--permission-mode acceptEdits" in seen[1]
    assert "dangerously" not in seen[1]
    assert len(slept) == 1 and slept[0] > 0
    event, fields = emitter.events[0]
    assert event == "usage_limited"
    assert fields["node_id"] == "M1.1" and fields["attempt"] == 1


def test_a_successful_run_never_waits(monkeypatch) -> None:
    seen = _runs(monkeypatch, [(0, "all done")])
    emitter = _Emitter()

    rc = gsi.run_implement_hook(
        CLAUDE, {}, Path("/repo"), emitter=emitter, sleep=lambda _s: pytest.fail("slept")
    )

    assert rc == 0 and len(seen) == 1 and emitter.events == []


def test_native_auto_continue_exiting_zero_is_left_alone(monkeypatch) -> None:
    """Claude 2.1.234+ can ride out the limit itself and still exit 0."""
    seen = _runs(monkeypatch, [(0, LIMIT + "resumed automatically\n")])

    rc = gsi.run_implement_hook(
        CLAUDE, {}, Path("/repo"), sleep=lambda _s: pytest.fail("slept")
    )

    assert rc == 0 and len(seen) == 1


def test_repeated_limits_stop_rather_than_loop(monkeypatch, capsys) -> None:
    seen = _runs(monkeypatch, [(1, _limit_text())] * (gsi.MAX_RESUMES + 1))

    rc = gsi.run_implement_hook(CLAUDE, {}, Path("/repo"), sleep=lambda _s: None)

    assert rc == 1
    assert len(seen) == gsi.MAX_RESUMES + 1
    assert "still rate-limited" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Refusing to wait
# ---------------------------------------------------------------------------


def test_a_spend_limit_stops_immediately(monkeypatch, capsys) -> None:
    _runs(monkeypatch, [(1, "You have reached your monthly spend limit.")])

    rc = gsi.run_implement_hook(CLAUDE, {}, Path("/repo"), sleep=lambda _s: pytest.fail("slept"))

    assert rc == 1
    assert "no reset time to wait for" in capsys.readouterr().err


def test_an_unrecognized_limit_stops_loudly(monkeypatch, capsys) -> None:
    """A format change must be visible, not absorbed as a normal failure."""
    _runs(monkeypatch, [(1, "API error 429: too many requests.")])

    rc = gsi.run_implement_hook(CLAUDE, {}, Path("/repo"), sleep=lambda _s: pytest.fail("slept"))

    assert rc == 1
    err = capsys.readouterr().err
    assert "output format may have changed" in err
    assert "429" in err


def test_an_ordinary_failure_is_reported_as_itself(monkeypatch) -> None:
    _runs(monkeypatch, [(3, "TypeError: cannot add str to int")])

    rc = gsi.run_implement_hook(CLAUDE, {}, Path("/repo"), sleep=lambda _s: pytest.fail("slept"))

    assert rc == 3


def test_a_timed_limit_with_no_session_id_stops_loudly(monkeypatch, capsys) -> None:
    """Resuming the wrong session would abandon the work already done."""
    _runs(monkeypatch, [(1, _limit_text(session=None))])

    rc = gsi.run_implement_hook(CLAUDE, {}, Path("/repo"), sleep=lambda _s: pytest.fail("slept"))

    assert rc == 1
    assert "could not find the session id" in capsys.readouterr().err


def test_a_reset_beyond_the_wait_ceiling_stops(monkeypatch, capsys) -> None:
    _runs(monkeypatch, [(1, _limit_text(minutes_ahead=9 * 60))])

    rc = gsi.run_implement_hook(CLAUDE, {}, Path("/repo"), sleep=lambda _s: pytest.fail("slept"))

    assert rc == 1
    assert "beyond the" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Timing and session discovery
# ---------------------------------------------------------------------------


def test_the_wait_includes_a_grace_period() -> None:
    reset = NOW + timedelta(minutes=30)

    assert gsi.seconds_until(reset, now=NOW) == 30 * 60 + gsi.GRACE_SECONDS


def test_a_reset_already_past_waits_no_negative_time() -> None:
    assert gsi.seconds_until(NOW - timedelta(hours=1), now=NOW) == 0.0


def test_the_session_id_comes_from_this_repos_transcripts(tmp_path, monkeypatch) -> None:
    repo = Path("/Users/x/WORKSPACE/app")
    projects = tmp_path / ".claude" / "projects"
    mine = projects / str(repo).replace("/", "-")
    other = projects / "-Users-x-WORKSPACE-other"
    for d in (mine, other):
        d.mkdir(parents=True)
    (other / "wrong-session.jsonl").write_text("{}", encoding="utf-8")
    (mine / "right-session.jsonl").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(gsi.Path, "home", classmethod(lambda _cls: tmp_path))

    assert gsi.latest_session_id(repo) == "right-session"


def test_no_claude_directory_means_no_session_id(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(gsi.Path, "home", classmethod(lambda _cls: tmp_path))

    assert gsi.latest_session_id(Path("/repo")) is None
