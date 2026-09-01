"""`specy-road history` — the surface an agentic IDE actually calls.

Covers the two output modes (human and `--json`) and the one case that has to
be handled rather than papered over: an id that several nodes have held.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from specy_road.history_index import clear_memo
from tests.test_history_walk import M01_KEY, commit, edit_node, git, repo

__all__ = ["repo"]  # re-exported fixture


@pytest.fixture(autouse=True)
def _no_memo() -> None:
    clear_memo()


def run(argv: list[str], repo: Path) -> int:
    from history_cli import main

    with pytest.raises(SystemExit) as exit_info:
        main([*argv, "--repo-root", str(repo)])
    return int(exit_info.value.code or 0)


def test_a_node_timeline_prints_oldest_first(repo: Path, capsys) -> None:
    edit_node(repo, "M2", status="In Progress")
    commit(repo, "start M2")
    edit_node(repo, "M2", status="Complete")
    commit(repo, "finish M2")

    assert run(["history", "M2"], repo) == 0
    lines = capsys.readouterr().out.splitlines()

    statuses = [ln for ln in lines if "status" in ln]
    assert "Not Started -> In Progress" in statuses[0]
    assert "In Progress -> Complete" in statuses[1]


def test_the_feed_lists_every_node_newest_first(repo: Path, capsys) -> None:
    edit_node(repo, "M2", status="In Progress")
    commit(repo, "start M2")

    assert run(["history"], repo) == 0
    out = capsys.readouterr().out

    assert out.splitlines()[0].count("status Not Started -> In Progress") == 1
    assert "event(s) from" in out


def test_json_carries_the_node_key_its_ids_and_its_events(repo: Path, capsys) -> None:
    assert run(["history", "M0.1", "--json"], repo) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["node_key"] == M01_KEY
    assert payload["ids"] == ["M0.1"]
    assert all(e["node_key"] == M01_KEY for e in payload["events"])
    assert all({"at", "commit", "kind", "seq"} <= set(e) for e in payload["events"])


def test_archived_flag_narrows_to_work_that_left_the_graph(
    repo: Path, capsys
) -> None:
    from specy_road.archive_ops import archive_node

    archive_node(repo, "M0.1")
    commit(repo, "archive M0.1")

    assert run(["history", "--archived", "--json"], repo) == 0
    events = json.loads(capsys.readouterr().out)["events"]

    assert {e["kind"] for e in events} == {"archived"}
    assert events[0]["node_key"] == M01_KEY


def test_since_filters_the_feed(repo: Path, capsys) -> None:
    assert run(["history", "--since", "2999-01-01"], repo) == 0
    assert "no matching events" in capsys.readouterr().out


def test_an_unknown_node_exits_one(repo: Path, capsys) -> None:
    assert run(["history", "M9.9"], repo) == 1
    assert "no node 'M9.9'" in capsys.readouterr().err


def test_an_ambiguous_id_exits_two_and_lists_the_candidates(
    repo: Path, capsys
) -> None:
    """Two nodes have held M0.1 and neither holds it now — say so, don't guess."""
    edit_node(repo, "M0.1", id="M0.8")
    commit(repo, "vacate M0.1")
    edit_node(repo, "M0.3", id="M0.1")
    commit(repo, "M0.3 takes the slot")
    edit_node(repo, "M0.1", id="M0.7")
    commit(repo, "vacate it again")

    assert run(["history", "M0.1"], repo) == 2
    err = capsys.readouterr().err

    assert "ambiguous" in err
    assert M01_KEY in err
    assert "M0.1 -> M0.8" in err


def test_a_node_key_is_accepted_directly(repo: Path, capsys) -> None:
    assert run(["history", M01_KEY], repo) == 0
    assert M01_KEY in capsys.readouterr().out


def test_rebuild_discards_the_cache_and_still_answers(repo: Path, capsys) -> None:
    from specy_road.history_cache import cache_path

    run(["history"], repo)
    cache_path(repo).write_text("garbage", encoding="utf-8")
    clear_memo()

    assert run(["history", "--rebuild"], repo) == 0
    assert "event(s) from" in capsys.readouterr().out


def test_a_non_repo_explains_that_history_comes_from_git(
    tmp_path: Path, capsys
) -> None:
    assert run(["history"], tmp_path) == 0
    assert "derived from git" in capsys.readouterr().out
