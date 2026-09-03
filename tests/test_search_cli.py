"""`specy-road search` — the surface an agent actually calls."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from tests.helpers import DOGFOOD

M01_KEY = "44ef4a9d-923f-545c-8187-eaabc7ca86ba"


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    dest = tmp_path / "repo"
    shutil.copytree(DOGFOOD, dest)
    return dest


def run(argv: list[str], root: Path) -> int:
    from specy_road.bundled_scripts.search_cli import main

    with pytest.raises(SystemExit) as exit_info:
        main([*argv, "--repo-root", str(root)])
    return int(exit_info.value.code or 0)


def test_a_prose_query_prints_path_context_and_snippet(repo: Path, capsys) -> None:
    assert run(["search", "contract"], repo) == 0
    out = capsys.readouterr().out

    assert "planning/M0.1_" in out
    assert "M0.1 Establish shared contracts" in out  # the derived context line
    assert "result(s)" in out


def test_multi_word_queries_are_joined(repo: Path, capsys) -> None:
    assert run(["search", "shared", "contracts"], repo) == 0
    assert "result(s)" in capsys.readouterr().out


def test_json_is_a_stable_envelope(repo: Path, capsys) -> None:
    assert run(["search", "contract", "--json", "--limit", "3"], repo) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["query"] == "contract"
    assert 0 < len(payload["results"]) <= 3
    for item in payload["results"]:
        assert {
            "score",
            "doc_path",
            "heading",
            "context",
            "snippet",
            "node_id",
            "node_key",
            "scope",
            "kind",
        } <= set(item)


def test_a_bare_node_id_works_without_a_special_flag(repo: Path, capsys) -> None:
    assert run(["search", "M0.1", "--json"], repo) == 0
    results = json.loads(capsys.readouterr().out)["results"]

    assert results and results[0]["node_id"] == "M0.1"


def test_scope_archived_narrows_to_work_that_left_the_graph(
    repo: Path, capsys
) -> None:
    from specy_road.archive_ops import archive_node

    archive_node(repo, "M0.1")

    assert run(["search", "contract", "--scope", "archived", "--json"], repo) == 0
    results = json.loads(capsys.readouterr().out)["results"]

    assert results and all(r["scope"] == "archived" for r in results)


def test_kind_and_node_filters_are_exposed(repo: Path, capsys) -> None:
    assert run(["search", "contract", "--kind", "planning", "--json"], repo) == 0
    results = json.loads(capsys.readouterr().out)["results"]
    assert results and all(r["kind"] == "planning" for r in results)

    assert run(["search", "contract", "--node", "M0.1", "--json"], repo) == 0
    results = json.loads(capsys.readouterr().out)["results"]
    assert results and all(r["node_id"] == "M0.1" for r in results)


def test_limit_is_honoured(repo: Path, capsys) -> None:
    assert run(["search", "contract", "--limit", "2", "--json"], repo) == 0
    assert len(json.loads(capsys.readouterr().out)["results"]) <= 2


def test_no_matches_suggests_what_to_try_next(repo: Path, capsys) -> None:
    assert run(["search", "zzzznotpresentzzzz"], repo) == 0
    out = capsys.readouterr().out

    assert "no matches" in out
    assert "--scope all" in out


def test_an_empty_query_exits_two(repo: Path, capsys) -> None:
    assert run(["search"], repo) == 2
    assert "nothing to search for" in capsys.readouterr().err


def test_stats_reports_index_size_and_backend(repo: Path, capsys) -> None:
    assert run(["search", "--stats", "--json"], repo) == 0
    stats = json.loads(capsys.readouterr().out)

    assert stats["chunks"] > 0 and stats["documents"] > 0
    assert stats["fts5"] is True


def test_an_empty_repo_says_nothing_is_indexed(tmp_path: Path, capsys) -> None:
    assert run(["search", "anything"], tmp_path) == 0
    assert "nothing indexed" in capsys.readouterr().out


def test_rebuild_still_answers(repo: Path, capsys) -> None:
    assert run(["search", "contract", "--rebuild"], repo) == 0
    assert "result(s)" in capsys.readouterr().out
