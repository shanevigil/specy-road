"""CR3: `session end` ends only the caller's own session, or an expired one (M21.32).

A peer started with `session start --agent peer`; the caller runs as another id
(`SPECY_ROAD_AGENT_ID=me`), the same `$USER`, as every local agent does.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from tests.review_repo_helpers import make_review_repo

from specy_road import session_presence as sp
from specy_road import tool_call_guard as g
from specy_road.bundled_scripts import session_cli

RULE = "is not yours (you are me); never end or override another agent's session (AGENTS.md, Shared checkouts)"


class _Stdin(io.StringIO):
    def __init__(self, tty: bool) -> None:
        super().__init__("")
        self._tty = tty

    def isatty(self) -> bool:
        return self._tty


def _cli(*args: str) -> int:
    with pytest.raises(SystemExit) as e:
        session_cli.main(list(args))
    return e.value.code or 0


@pytest.mark.parametrize("ttl, caller, args, tty, code, kept, says", [
    ("4", "me", ["peer"], False, 1, True, RULE),
    ("4", "me", ["--agent", "peer"], False, 1, True, RULE),
    ("4", "me", [], False, 0, True, "session me: no record; your record is under the id `session start` printed"),
    ("-1", "me", ["peer"], False, 0, False, "session peer: ended"),
    ("4", "peer", [], False, 0, False, "session peer: ended"),
    ("4", "me", ["peer", "--force"], False, 1, True,
     "a human ends another agent's live session from a terminal; nothing was removed"),
    ("4", "me", ["peer", "--force"], True, 0, False, "session peer: ended"),
], ids=["end-peer", "end-agent-peer", "no-own-record", "expired-peer", "own-id", "force-no-tty", "force-tty"])
def test_session_end_only_your_own(tmp_path: Path, capsys, monkeypatch, ttl, caller, args, tty, code, kept, says) -> None:
    repo = make_review_repo(tmp_path)
    monkeypatch.setenv("SPECY_ROAD_AGENT_ID", "me")
    assert _cli("session", "start", "--agent", "peer", "--path", "docs/", f"--ttl-hours={ttl}",
                "--repo-root", str(repo)) == 0
    record = sp.session_path(repo, "peer")
    before = record.read_bytes()
    capsys.readouterr()
    monkeypatch.setenv("SPECY_ROAD_AGENT_ID", caller)
    monkeypatch.setattr("sys.stdin", _Stdin(tty))
    assert _cli("session", "end", *args, "--repo-root", str(repo)) == code
    out = capsys.readouterr()
    assert says in (out.err if code else out.out)
    assert "peer" not in out.out or not kept       # no other session listed
    if kept:
        assert record.read_bytes() == before
    else:
        assert not record.exists()


def test_guard_denial_names_the_rule(tmp_path: Path, monkeypatch) -> None:
    repo = make_review_repo(tmp_path)
    monkeypatch.chdir(repo)                        # the peer works in this worktree
    monkeypatch.setenv("SPECY_ROAD_AGENT_ID", "me")
    assert _cli("session", "start", "--agent", "peer", "--path", "docs/", "--repo-root", str(repo)) == 0
    v = g.decide(repo, "git restore src/app.css", agent="me")
    assert not v.allowed
    assert "Do not end, edit or delete another session's record to get past this; ask its owner or a human." in v.reason
