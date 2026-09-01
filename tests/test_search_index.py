"""Building, updating and querying the FTS5 index.

The properties that matter: it reflects the working tree (not HEAD), it rebuilds
rather than misleads when anything is off, current work outranks superseded
work, and the same passage is never returned twice.
"""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from specy_road.search_corpus import SCOPE_ARCHIVED, SCOPE_LIVE
from specy_road.search_index import (
    INDEX_VERSION,
    corpus_stats,
    fts5_available,
    index_path,
    refresh,
    search,
)
from tests.helpers import DOGFOOD

M01_KEY = "44ef4a9d-923f-545c-8187-eaabc7ca86ba"


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    dest = tmp_path / "repo"
    shutil.copytree(DOGFOOD, dest)
    return dest


def sheet_for(repo: Path, node_id: str) -> Path:
    return next((repo / "planning").glob(f"{node_id}_*.md"))


def paths_of(results: list[dict]) -> list[str]:
    return [r["doc_path"] for r in results]


# --- build ------------------------------------------------------------------


def test_this_interpreter_has_fts5() -> None:
    """If this ever fails the fallback carries the feature — but say so loudly."""
    assert fts5_available()


def test_a_cold_build_indexes_the_corpus(repo: Path) -> None:
    stats = corpus_stats(repo)

    assert stats["documents"] > 0 and stats["chunks"] > stats["documents"]
    assert index_path(repo).is_file()


def test_the_index_lives_in_the_gitignored_cache_directory(repo: Path) -> None:
    corpus_stats(repo)
    assert index_path(repo).relative_to(repo).parts[:2] == (".specyrd", "cache")


def test_an_unchanged_tree_does_no_work_on_the_second_pass(repo: Path) -> None:
    refresh(repo)
    before = index_path(repo).stat().st_mtime_ns

    refresh(repo)

    assert index_path(repo).stat().st_mtime_ns == before


# --- incremental ------------------------------------------------------------


def test_an_edit_is_picked_up_without_a_rebuild(repo: Path) -> None:
    """Working-tree accurate, unlike the HEAD-keyed history index."""
    assert not search(repo, "quokka")

    sheet = sheet_for(repo, "M0.1")
    sheet.write_text(
        sheet.read_text(encoding="utf-8") + "\n## Notes\n\nA quokka appeared.\n",
        encoding="utf-8",
    )

    results = search(repo, "quokka")
    assert results and results[0]["doc_path"] == f"planning/{sheet.name}"


def test_only_the_changed_document_is_re_chunked(repo: Path) -> None:
    con = refresh(repo)
    rowids = {
        r["doc_path"]: r["n"]
        for r in con.execute(
            "SELECT doc_path, COUNT(*) AS n FROM chunks GROUP BY doc_path"
        )
    }
    sheet = sheet_for(repo, "M0.1")
    rel = f"planning/{sheet.name}"
    sheet.write_text(sheet.read_text(encoding="utf-8") + "\n## Extra\n\nx\n", "utf-8")

    con = refresh(repo)
    after = {
        r["doc_path"]: r["n"]
        for r in con.execute(
            "SELECT doc_path, COUNT(*) AS n FROM chunks GROUP BY doc_path"
        )
    }

    assert after[rel] == rowids[rel] + 1
    assert {k: v for k, v in after.items() if k != rel} == {
        k: v for k, v in rowids.items() if k != rel
    }


def test_a_deleted_document_leaves_no_chunks_behind(repo: Path) -> None:
    sheet = sheet_for(repo, "M0.1")
    rel = f"planning/{sheet.name}"
    refresh(repo)
    sheet.unlink()

    con = refresh(repo)

    assert con.execute(
        "SELECT COUNT(*) FROM chunks WHERE doc_path = ?", (rel,)
    ).fetchone()[0] == 0


# --- invalidation -----------------------------------------------------------


def test_a_version_bump_discards_the_index(repo: Path) -> None:
    refresh(repo)
    con = sqlite3.connect(index_path(repo))
    con.execute(
        "INSERT OR REPLACE INTO meta VALUES ('version', ?)", (str(INDEX_VERSION + 1),)
    )
    con.commit()
    con.close()

    assert corpus_stats(repo)["chunks"] > 0  # rebuilt, not read


def test_a_corrupt_index_file_rebuilds_without_raising(repo: Path) -> None:
    refresh(repo)
    index_path(repo).write_bytes(b"not a sqlite database at all")

    assert corpus_stats(repo)["chunks"] > 0


def test_rebuild_starts_from_nothing(repo: Path) -> None:
    refresh(repo)
    sheet_for(repo, "M0.1").unlink()

    con = refresh(repo, rebuild=True)

    assert con.execute(
        "SELECT COUNT(*) FROM chunks WHERE doc_path LIKE 'planning/M0.1%'"
    ).fetchone()[0] == 0


def test_an_unwritable_cache_location_degrades_to_no_results(repo: Path) -> None:
    (repo / ".specyrd").write_text("this is a file, not a directory", encoding="utf-8")

    assert refresh(repo) is None
    assert corpus_stats(repo) == {"documents": 0, "chunks": 0}


# --- ranking ----------------------------------------------------------------


def test_a_prose_query_finds_the_relevant_section(repo: Path) -> None:
    results = search(repo, "contract")
    assert results
    assert any("contract" in r["snippet"].lower() for r in results)


def test_a_bare_node_id_finds_that_node_via_the_structural_list(repo: Path) -> None:
    """RRF fuses the exact-identifier match with the text match."""
    results = search(repo, "M0.1", limit=5)

    assert results
    assert all(r["node_id"] == "M0.1" for r in results[:2])


def test_a_node_key_resolves_directly(repo: Path) -> None:
    results = search(repo, M01_KEY, limit=3)
    assert results and results[0]["node_key"] == M01_KEY


def test_every_result_carries_its_derived_context(repo: Path) -> None:
    for item in search(repo, "contract", limit=5):
        assert item["context"]
        assert item["doc_path"] and item["scope"] and item["kind"]


def test_the_same_passage_is_never_returned_twice(repo: Path) -> None:
    """Duplicate text wastes the context this feature exists to protect."""
    duplicate = "An identical paragraph about widgets.\n"
    for node_id in ("M0.1", "M0.3"):
        sheet = sheet_for(repo, node_id)
        sheet.write_text(
            sheet.read_text(encoding="utf-8") + f"\n## Dup\n\n{duplicate}",
            encoding="utf-8",
        )

    results = search(repo, "widgets", limit=10)

    assert len(results) == 1


def test_a_query_matching_nothing_returns_nothing(repo: Path) -> None:
    assert search(repo, "zzzznotpresentzzzz") == []


def test_an_empty_query_returns_nothing(repo: Path) -> None:
    assert search(repo, "   ") == []


def test_punctuation_heavy_queries_do_not_break_fts5_syntax(repo: Path) -> None:
    """A raw query is quoted per term, so operator characters are literal."""
    for query in ('AND OR NOT', '"unbalanced', 'M0.1*', 'a-b-c', '((('):
        assert isinstance(search(repo, query), list)


# --- scope ------------------------------------------------------------------


def test_archived_material_is_searchable_and_marked(repo: Path) -> None:
    from specy_road.archive_ops import archive_node

    archive_node(repo, "M0.1")

    results = search(repo, "contract", limit=20)
    archived = [r for r in results if r["scope"] == SCOPE_ARCHIVED]

    assert archived
    assert all(r["node_id"] == "M0.1" for r in archived if r["node_id"])


def test_scope_filters_narrow_the_answer(repo: Path) -> None:
    from specy_road.archive_ops import archive_node

    archive_node(repo, "M0.1")

    live_only = search(repo, "contract", scopes={SCOPE_LIVE}, limit=20)
    archived_only = search(repo, "contract", scopes={SCOPE_ARCHIVED}, limit=20)

    assert live_only and all(r["scope"] == SCOPE_LIVE for r in live_only)
    assert archived_only and all(r["scope"] == SCOPE_ARCHIVED for r in archived_only)


def test_a_live_hit_outranks_an_identical_archived_one(repo: Path) -> None:
    """Latest wins by default; the archived copy is demoted, not hidden."""
    from specy_road.archive_ops import archive_node

    marker = "distinctivephrase"
    sheet = sheet_for(repo, "M0.1")
    sheet.write_text(
        sheet.read_text(encoding="utf-8") + f"\n## Marker\n\n{marker} here\n",
        encoding="utf-8",
    )
    archive_node(repo, "M0.1")
    # Recreate a live sheet carrying the same phrase.
    (repo / "planning" / "M0.3_api-contract-outline_cd44fef1-715a-5b8d-b03f-1752a61a47cc.md").write_text(
        f"## Intent\n\n{marker} here too\n", encoding="utf-8"
    )

    results = search(repo, marker, limit=5)

    assert results[0]["scope"] == SCOPE_LIVE
    assert any(r["scope"] == SCOPE_ARCHIVED for r in results)


def test_kind_and_node_filters_apply(repo: Path) -> None:
    from specy_road.search_corpus import KIND_PLANNING

    only_planning = search(repo, "contract", kinds={KIND_PLANNING}, limit=20)
    assert only_planning and all(r["kind"] == KIND_PLANNING for r in only_planning)

    only_m01 = search(repo, "contract", node_id="M0.1", limit=20)
    assert only_m01 and all(r["node_id"] == "M0.1" for r in only_m01)


# --- fallback ---------------------------------------------------------------


def test_the_no_fts5_fallback_answers_the_same_question(
    repo: Path, monkeypatch
) -> None:
    with_fts5 = paths_of(search(repo, "contract", limit=5))

    monkeypatch.setattr("specy_road.search_index.fts5_available", lambda: False)
    without = search(repo, "contract", limit=5)

    assert without
    # Scoring is a weighted term count rather than BM25, so the ordering is
    # coarser by design — what must hold is that it finds the same material.
    assert set(paths_of(without)) & set(with_fts5)
    assert all(r["context"] and r["snippet"] for r in without)


def test_the_fallback_still_honours_filters(repo: Path, monkeypatch) -> None:
    monkeypatch.setattr("specy_road.search_index.fts5_available", lambda: False)

    results = search(repo, "contract", scopes={SCOPE_LIVE}, limit=5)

    assert results and all(r["scope"] == SCOPE_LIVE for r in results)
