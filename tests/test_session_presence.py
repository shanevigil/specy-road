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
    # Alice herself is clear, and ends her own record.
    assert _cli("session", "check", "--agent", "alice", "--repo-root", str(repo)) == 0
    monkeypatch.setenv("SPECY_ROAD_AGENT_ID", "alice")
    assert _cli("session", "end", "--repo-root", str(repo)) == 0
    monkeypatch.setenv("SPECY_ROAD_AGENT_ID", "me")
    assert _cli("session", "check", "--repo-root", str(repo)) == 0


def test_cli_end_with_an_id_retires_only_the_same_users_session(tmp_path: Path, capsys, monkeypatch) -> None:
    repo = make_review_repo(tmp_path)
    monkeypatch.setenv("SPECY_ROAD_AGENT_ID", "me")
    monkeypatch.setenv("USER", "carol")
    sp.start_session(repo, "carol-s111", paths=["src"])      # a terminal of hers that has since closed
    monkeypatch.setenv("USER", "dave")
    sp.start_session(repo, "dave-s222", paths=["docs"])
    assert _cli("session", "end", "carol-s111", "--repo-root", str(repo)) == 1
    assert "started by user 'carol', not 'dave'; only its owner may end it" in capsys.readouterr().err
    monkeypatch.setenv("SPECY_ROAD_AGENT_ID", "dave-s222")
    assert _cli("session", "end", "dave-s222", "--repo-root", str(repo)) == 0
    assert "session dave-s222: ended" in capsys.readouterr().out
    assert [s.agent for s in sp.list_sessions(repo)] == ["carol-s111"]
    assert _cli("session", "end", "dave-s222", "--repo-root", str(repo)) == 0
    assert "no record" in capsys.readouterr().out
    assert _cli("session", "end", "../x", "--repo-root", str(repo)) == 1


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


def _derived_end(repo: Path, monkeypatch, sid: int) -> int:
    """`session end` with no id from a shell whose POSIX session differs from start's."""
    monkeypatch.delenv("SPECY_ROAD_AGENT_ID", raising=False)
    monkeypatch.setattr(sp.os, "getsid", lambda _pid: sid)
    return _cli("session", "end", "--repo-root", str(repo))


def test_cli_start_prints_the_id_to_export(tmp_path: Path, capsys, monkeypatch) -> None:
    repo = make_review_repo(tmp_path)
    monkeypatch.delenv("SPECY_ROAD_AGENT_ID", raising=False)
    monkeypatch.setenv("USER", "erin")
    monkeypatch.setattr(sp.os, "getsid", lambda _pid: 101)
    assert _cli("session", "start", "--path", "src", "--repo-root", str(repo)) == 0
    out = capsys.readouterr().out
    assert out.startswith("session erin-s101:")
    assert "export SPECY_ROAD_AGENT_ID=erin-s101\n" in out
    assert out.index("erin-s101") < out.index("export SPECY_ROAD_AGENT_ID=")


def test_cli_end_with_a_new_derived_id_ends_nothing_and_names_the_exported_id(
    tmp_path: Path, capsys, monkeypatch,
) -> None:
    """No fallback: a derived id with no record ends none of this user's sessions, here or elsewhere."""
    repo = make_review_repo(tmp_path)
    git(repo, "branch", "-q", "feature/rm-wt2")
    wt2 = tmp_path / "wt2"
    git(repo, "worktree", "add", "-q", str(wt2), "feature/rm-wt2")
    monkeypatch.setenv("USER", "frank")
    hint = ("session frank-s999: no record; your record is under the id `session start` printed "
            "(export SPECY_ROAD_AGENT_ID=<id>)\n")
    # The user's only live session, on this worktree and branch: once a fallback, now kept.
    sp.start_session(repo, "frank-s101", paths=["src"], worktree=repo)
    monkeypatch.chdir(repo)
    assert _derived_end(repo, monkeypatch, 999) == 0
    out = capsys.readouterr()
    assert out.out == hint and out.err == ""
    sp.start_session(repo, "frank-s201", paths=["docs"], worktree=wt2)
    assert _derived_end(repo, monkeypatch, 999) == 0
    out = capsys.readouterr()
    assert out.out == hint and out.err == ""             # lists no other sessions
    assert [s.agent for s in sp.list_sessions(repo)] == ["frank-s101", "frank-s201"]


def test_cli_touch_from_subdirectory_then_derived_end_with_another_worktree(
    tmp_path: Path, capsys, monkeypatch,
) -> None:
    repo = make_review_repo(tmp_path)
    git(repo, "branch", "-q", "feature/rm-wt2")
    wt2 = tmp_path / "wt2"
    git(repo, "worktree", "add", "-q", str(wt2), "feature/rm-wt2")
    monkeypatch.setenv("USER", "iris")
    monkeypatch.delenv("SPECY_ROAD_AGENT_ID", raising=False)
    monkeypatch.setattr(sp.os, "getsid", lambda _pid: 101)
    monkeypatch.chdir(repo)
    assert _cli("session", "start", "--path", "src", "--repo-root", str(repo)) == 0
    capsys.readouterr()
    sp.start_session(repo, "iris-wt2", paths=["docs"], worktree=wt2)
    monkeypatch.setattr(sp.os, "getsid", lambda _pid: 202)
    monkeypatch.chdir(repo / "src")
    assert _cli("session", "touch", "--repo-root", str(repo)) == 0
    capsys.readouterr()
    main = sp.load_session(sp.session_path(repo, "iris-s101"))
    assert main is not None and main.worktree == str(sp.git_worktree_top(repo))
    assert _derived_end(repo, monkeypatch, 101) == 0      # end names its own id only
    assert capsys.readouterr().out == "session iris-s101: ended\n"
    assert [s.agent for s in sp.list_sessions(repo)] == ["iris-wt2"]


def test_cli_start_from_subdirectory_then_derived_end(tmp_path: Path, capsys, monkeypatch) -> None:
    repo = make_review_repo(tmp_path)
    git(repo, "branch", "-q", "feature/rm-wt2")
    wt2 = tmp_path / "wt2"
    git(repo, "worktree", "add", "-q", str(wt2), "feature/rm-wt2")
    monkeypatch.setenv("USER", "jake")
    monkeypatch.delenv("SPECY_ROAD_AGENT_ID", raising=False)
    monkeypatch.setattr(sp.os, "getsid", lambda _pid: 401)
    monkeypatch.chdir(repo / "src")
    assert _cli("session", "start", "--path", "src", "--repo-root", str(repo)) == 0
    capsys.readouterr()
    sp.start_session(repo, "jake-wt2", paths=["docs"], worktree=wt2)
    monkeypatch.chdir(repo / "docs")
    assert _derived_end(repo, monkeypatch, 401) == 0
    assert capsys.readouterr().out == "session jake-s401: ended\n"
    assert [s.agent for s in sp.list_sessions(repo)] == ["jake-wt2"]


def test_cli_touch_with_a_new_derived_id_renews_the_session_on_this_worktree(
    tmp_path: Path, capsys, monkeypatch,
) -> None:
    repo = make_review_repo(tmp_path)
    monkeypatch.setenv("USER", "helen")
    monkeypatch.delenv("SPECY_ROAD_AGENT_ID", raising=False)
    monkeypatch.setattr(sp.os, "getsid", lambda _pid: 101)
    sp.start_session(repo, "helen-s101", paths=["src"], worktree=repo)
    monkeypatch.setattr(sp.os, "getsid", lambda _pid: 202)
    monkeypatch.chdir(repo)
    assert _cli("session", "touch", "--repo-root", str(repo)) == 0
    out = capsys.readouterr().out
    assert out.startswith("session helen-s101:")
    assert [s.agent for s in sp.list_sessions(repo)] == ["helen-s101"]


def test_cli_end_with_an_explicit_id_never_falls_back(tmp_path: Path, capsys, monkeypatch) -> None:
    repo = make_review_repo(tmp_path)
    monkeypatch.setenv("USER", "frank")
    sp.start_session(repo, "frank-s101", paths=["src"])
    monkeypatch.setenv("SPECY_ROAD_AGENT_ID", "frank-other")
    assert _cli("session", "end", "--repo-root", str(repo)) == 0
    assert _cli("session", "end", "--agent", "frank-x", "--repo-root", str(repo)) == 0
    assert capsys.readouterr().out.count("no record") == 2
    assert [s.agent for s in sp.list_sessions(repo)] == ["frank-s101"]
