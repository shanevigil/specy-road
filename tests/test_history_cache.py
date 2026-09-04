"""Caching and incremental rebuild of the roadmap history index.

The contract is that the cache is never trusted over git: anything unexpected —
a version bump, a corrupt file, a rewritten history — costs a rebuild and never
a wrong answer or a raised exception. These tests try to make it lie.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from specy_road.history_cache import (
    CACHE_VERSION,
    cache_path,
    load_cache,
    save_cache,
)
from specy_road.history_index import (
    clear_memo,
    feed,
    history_index,
    node_timeline,
    resolve_node_key,
)
from tests.test_history_walk import (
    M01_KEY,
    M03_KEY,
    M2_KEY,
    commit,
    edit_node,
    git,
    repo,
)

__all__ = ["repo"]  # re-exported fixture


@pytest.fixture(autouse=True)
def _no_memo() -> None:
    """The in-process memo would mask every on-disk cache behaviour here."""
    clear_memo()


def index(root: Path, **kw: object) -> dict:
    return history_index(root, **kw)


def test_a_cold_build_writes_the_cache(repo: Path) -> None:
    doc = index(repo)

    assert doc["events"]
    assert doc["head"] == git(repo, "rev-parse", "HEAD")
    assert cache_path(repo).is_file()
    assert load_cache(repo)["last_indexed_commit"] == doc["head"]


def test_the_cache_lives_under_dot_specyrd_cache(repo: Path) -> None:
    """`.specyrd/manifest.json` is tracked; only `cache/` is ignored."""
    index(repo)
    rel = cache_path(repo).relative_to(repo)
    assert rel.parts[:2] == (".specyrd", "cache")


def test_an_unmoved_head_reuses_the_cache_verbatim(repo: Path) -> None:
    first = index(repo)
    clear_memo()
    second = index(repo)

    assert second == first


def test_a_new_commit_is_appended_not_rebuilt(repo: Path) -> None:
    before = index(repo)
    edit_node(repo, "M2", status="In Progress")
    commit(repo, "start M2")
    clear_memo()

    after = index(repo)

    assert after["events"][: len(before["events"])] == before["events"]
    assert len(after["events"]) > len(before["events"])
    assert after["head"] == git(repo, "rev-parse", "HEAD")


def test_incremental_matches_a_full_rebuild(repo: Path) -> None:
    """The whole point: appending must not diverge from starting over."""
    index(repo)
    edit_node(repo, "M2", status="In Progress")
    commit(repo, "start M2")
    edit_node(repo, "M0.1", title="Contracts, revisited")
    commit(repo, "retitle M0.1")
    clear_memo()

    incremental = index(repo)
    clear_memo()
    full = index(repo, rebuild=True)

    assert incremental["events"] == full["events"]


def test_a_version_bump_discards_the_cache(repo: Path) -> None:
    index(repo)
    doc = json.loads(cache_path(repo).read_text(encoding="utf-8"))
    doc["cache_version"] = CACHE_VERSION + 1
    doc["events"] = [{"kind": "bogus"}]
    cache_path(repo).write_text(json.dumps(doc), encoding="utf-8")
    clear_memo()

    assert load_cache(repo) is None
    assert not any(e["kind"] == "bogus" for e in index(repo)["events"])


def test_a_corrupt_cache_rebuilds_without_raising(repo: Path) -> None:
    index(repo)
    cache_path(repo).write_text("{not json at all", encoding="utf-8")
    clear_memo()

    assert load_cache(repo) is None
    assert index(repo)["events"]


def test_a_truncated_cache_document_rebuilds(repo: Path) -> None:
    index(repo)
    cache_path(repo).write_text('{"cache_version": 1}', encoding="utf-8")
    clear_memo()

    assert load_cache(repo) is None
    assert index(repo)["events"]


def test_rewritten_history_rebuilds_rather_than_appending(repo: Path) -> None:
    """After an amend the cached commit is unreachable; its events are garbage."""
    edit_node(repo, "M2", status="In Progress")
    commit(repo, "start M2")
    index(repo)
    stale = load_cache(repo)["last_indexed_commit"]

    edit_node(repo, "M2", status="Blocked")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "--amend", "-m", "start M2, amended")
    clear_memo()

    doc = index(repo)

    assert doc["last_indexed_commit"] != stale
    statuses = [e for e in doc["events"] if e["kind"] == "status"]
    assert [e["to"] for e in statuses] == ["Blocked"]


def test_an_unwritable_cache_still_returns_results(repo: Path, monkeypatch) -> None:
    """A read-only checkout costs a rebuild each time, never a failed command."""
    monkeypatch.setattr("specy_road.history_index.save_cache", lambda *a, **k: False)
    clear_memo()

    doc = index(repo)

    assert doc["events"]
    assert not cache_path(repo).exists()


def test_save_cache_reports_failure_instead_of_raising(tmp_path: Path) -> None:
    blocked = tmp_path / "ro"
    blocked.mkdir()
    (blocked / ".specyrd").write_text("not a directory", encoding="utf-8")

    assert save_cache(blocked, {"cache_version": CACHE_VERSION}) is False


def test_a_non_repo_yields_an_empty_index(tmp_path: Path) -> None:
    doc = history_index(tmp_path)
    assert doc["events"] == [] and doc["head"] is None


# --- queries ----------------------------------------------------------------


def test_node_timeline_is_oldest_first_and_scoped_to_one_node(repo: Path) -> None:
    edit_node(repo, "M2", status="In Progress")
    commit(repo, "start M2")

    timeline = node_timeline(index(repo), M2_KEY)

    assert {e["node_key"] for e in timeline} == {M2_KEY}
    assert [e["at"] for e in timeline] == sorted(e["at"] for e in timeline)
    assert timeline[-1]["kind"] == "status"


def test_feed_is_newest_first_and_honours_limit(repo: Path) -> None:
    edit_node(repo, "M2", status="In Progress")
    commit(repo, "start M2")

    recent = feed(index(repo), limit=1)

    assert len(recent) == 1
    assert recent[0]["kind"] == "status"


def test_feed_since_filters_by_date_prefix(repo: Path) -> None:
    doc = index(repo)
    assert feed(doc, since="1999-01-01") == feed(doc)
    assert feed(doc, since="2999-01-01") == []


def test_resolve_accepts_a_live_id_and_a_raw_node_key(repo: Path) -> None:
    doc = index(repo)

    assert resolve_node_key(repo, "M0.1", doc) == (M01_KEY, [])
    assert resolve_node_key(repo, M01_KEY.upper(), doc) == (M01_KEY, [])


def test_resolve_finds_an_archived_node_by_id(repo: Path) -> None:
    """Archived work is gone from the live graph but still addressable."""
    from specy_road.archive_ops import archive_node

    archive_node(repo, "M0.1")
    commit(repo, "archive M0.1")

    assert resolve_node_key(repo, "M0.1", index(repo)) == (M01_KEY, [])


def test_an_id_two_nodes_have_held_is_reported_as_ambiguous(repo: Path) -> None:
    """An id is a position in the outline, not an identity — never guess.

    M0.1 is vacated, reused by another node, then vacated again, so nothing
    live or archived holds it and only history can answer — with two answers.
    """
    edit_node(repo, "M0.1", id="M0.8")
    commit(repo, "renumber M0.1 out of the way")
    edit_node(repo, "M0.3", id="M0.1")
    commit(repo, "M0.3 takes over the M0.1 slot")
    edit_node(repo, "M0.1", id="M0.7")
    commit(repo, "vacate M0.1 again")

    key, candidates = resolve_node_key(repo, "M0.1", index(repo))

    assert key is None
    assert set(candidates) == {M01_KEY, M03_KEY}


def test_an_unknown_id_resolves_to_nothing(repo: Path) -> None:
    assert resolve_node_key(repo, "M9.9", index(repo)) == (None, [])
