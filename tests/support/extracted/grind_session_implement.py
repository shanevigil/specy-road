"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

from datetime import datetime
from specy_road.orchestration.grind import grind_session_implement as gsi
import pytest
from datetime import timedelta
from datetime import timezone

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
