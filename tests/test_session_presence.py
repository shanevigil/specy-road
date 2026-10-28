"""Presence records under work/.sessions/ (design note decisions 5 and 6)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from tests.review_repo_helpers import NODE, git, make_review_repo

from specy_road import session_presence as sp
from specy_road.bundled_scripts import review_cli, session_cli
from specy_road.bundled_scripts.do_next_prompt import print_pickup_header


def _cli(*args: str) -> int:
    with pytest.raises(SystemExit) as e:
        session_cli.main(list(args))
    return e.value.code or 0


def test_start_touch_end_round_trip(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    s = sp.start_session(repo, "alice", paths=["src/", "docs/x.md"], note="refactor")
    assert s.branch == "feature/rm-thing" and s.paths == ["docs/x.md", "src"]
    assert s.is_live()
    again = sp.start_session(repo, "alice", paths=["src"])
    assert again.started == s.started and again.paths == ["src"] and again.note == "refactor"
    assert [x.agent for x in sp.list_sessions(repo)] == ["alice"]
    assert sp.end_session(repo, "alice") and not sp.end_session(repo, "alice")
    assert sp.list_sessions(repo) == []


def test_expired_sessions_are_ignored(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    sp.start_session(repo, "old", paths=["src"], ttl_hours=1)
    later = datetime.now(timezone.utc) + timedelta(hours=2)
    assert sp.list_sessions(repo, now=later) == []
    assert len(sp.list_sessions(repo, live_only=False)) == 1
    assert sp.conflicts(repo, ["src/a.py"], now=later) == []


def test_sessions_live_in_the_main_worktree(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    git(repo, "checkout", "-q", "dev")
    wt = tmp_path / "wt"
    git(repo, "worktree", "add", "-q", str(wt), "feature/rm-thing")
    s = sp.start_session(wt, "bob", paths=["src"], worktree=wt)
    assert s.path == sp.session_path(repo, "bob") and s.branch == "feature/rm-thing"
    assert [x.agent for x in sp.list_sessions(repo)] == ["bob"]


def test_conflicts_match_either_direction_and_exclude_self(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    sp.start_session(repo, "alice", paths=["src/api"])
    assert sp.conflicts(repo, ["src/api/routes.py"])  # inside her path
    assert sp.conflicts(repo, ["src"])                 # contains her path
    assert not sp.conflicts(repo, ["docs"])
    assert sp.conflicts(repo, ["src"], exclude="alice") == []


def test_bad_agent_id_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        sp.session_path(tmp_path, "../escape")


def test_cli_check_is_a_commit_guard(tmp_path: Path, capsys, monkeypatch) -> None:
    repo = make_review_repo(tmp_path)
    monkeypatch.setenv("SPECY_ROAD_AGENT_ID", "me")
    assert _cli("session", "start", "--agent", "alice", "--path", "src", "--repo-root", str(repo)) == 0
    (repo / "src" / "b.py").write_text("x\n")
    git(repo, "add", "src/b.py")
    assert _cli("session", "check", "--repo-root", str(repo)) == 1
    err = capsys.readouterr().err
    assert "overlap live session 'alice'" in err and "refuse" in err
    assert _cli("session", "check", "--path", "docs/x.md", "--repo-root", str(repo)) == 0
    # Alice herself is clear.
    assert _cli("session", "check", "--agent", "alice", "--repo-root", str(repo)) == 0
    assert _cli("session", "end", "--agent", "alice", "--repo-root", str(repo)) == 0
    assert _cli("session", "check", "--repo-root", str(repo)) == 0


def test_cli_start_warns_on_overlap_and_list_shows_sessions(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path)
    assert _cli("session", "start", "--agent", "alice", "--path", "src", "--repo-root", str(repo)) == 0
    capsys.readouterr()
    assert _cli("session", "start", "--agent", "bob", "--path", "src/a.py", "--note", "fix", "--repo-root", str(repo)) == 0
    assert "overlap live session 'alice'" in capsys.readouterr().err
    assert _cli("session", "list", "--json", "--repo-root", str(repo)) == 0
    rows = json.loads(capsys.readouterr().out)
    assert [r["agent"] for r in rows] == ["alice", "bob"] and rows[1]["note"] == "fix"


def test_pickup_header_warns_on_session_overlap(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path)
    sp.start_session(repo, "alice", paths=["src/thing"])
    print_pickup_header(NODE, "feature/rm-thing", repo)
    assert "M1.1's touch zones overlap live session 'alice'" in capsys.readouterr().err
    print_pickup_header(NODE, "feature/rm-thing")  # no root: no lookup, no crash
    assert "sessions:" not in capsys.readouterr().err


def test_handoff_status_lists_live_sessions(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path)
    sp.start_session(repo, "alice", paths=["src"])
    with pytest.raises(SystemExit):
        review_cli.main(["handoff", "status", "--repo-root", str(repo)])
    out = capsys.readouterr().out
    assert out.startswith("Live sessions: alice (feature/rm-thing: src)")
    with pytest.raises(SystemExit):
        review_cli.main(["handoff", "status", "--json", "--repo-root", str(repo)])
    data = json.loads(capsys.readouterr().out)
    assert data["sessions"][0]["agent"] == "alice" and data["nodes"] == []
