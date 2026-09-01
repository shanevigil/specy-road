"""What gets indexed, how it is cut up, and the context derived for each chunk.

The derived context is the load-bearing idea: Contextual Retrieval pays an LLM
to write a per-chunk summary because generic prose has no structure to read,
whereas every sheet here already maps to a node. These tests pin that the
structure actually reaches the index.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from specy_road.search_corpus import (
    KIND_CONSTITUTION,
    KIND_NODE,
    KIND_PLANNING,
    KIND_SHARED,
    KIND_SUMMARY,
    SCOPE_ARCHIVED,
    SCOPE_LIVE,
    build_node_info,
    derive_context,
)
from specy_road.search_sources import chunks_for, iter_source_files, node_body
from tests.helpers import DOGFOOD

M01_KEY = "44ef4a9d-923f-545c-8187-eaabc7ca86ba"


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    dest = tmp_path / "repo"
    shutil.copytree(DOGFOOD, dest)
    return dest


def all_chunks(root: Path) -> list:
    info = build_node_info(root)
    by_id = {v["id"]: v for v in info.values() if v.get("id")}
    out = []
    for source in iter_source_files(root):
        out.extend(chunks_for(root, source.path, info, by_id))
    return out


def paths(root: Path) -> list[str]:
    return [s.path for s in iter_source_files(root)]


# --- what is watched --------------------------------------------------------


def test_primary_sources_are_watched(repo: Path) -> None:
    watched = paths(repo)
    assert any(p.startswith("planning/") for p in watched)
    assert "shared/api-contract.md" in watched
    assert "roadmap/phases/M0.json" in watched


def test_only_manifest_named_chunks_are_watched(repo: Path) -> None:
    """The manifest is the live/archived boundary; an unlisted chunk is invisible."""
    (repo / "roadmap" / "phases" / "orphan.json").write_text(
        '{"nodes": []}', encoding="utf-8"
    )
    assert "roadmap/phases/orphan.json" not in paths(repo)


def test_briefs_are_never_indexed(repo: Path) -> None:
    """A brief re-inlines planning sheets and every shared contract verbatim."""
    work = repo / "work"
    work.mkdir()
    (work / "brief-M0.1.md").write_text("## 1. Execution target\n\nx\n", encoding="utf-8")

    assert not [p for p in paths(repo) if "brief-" in p]


def test_a_pr_body_is_indexed_only_when_its_summary_file_is_gone(repo: Path) -> None:
    """finish-this-task deletes the summary but keeps the pr-body as the record."""
    work = repo / "work"
    work.mkdir()
    (work / "pr-body-M0.1.md").write_text(
        "# [M0.1]\n\n## Implementation summary (dev-authored)\n\nDid the thing.\n",
        encoding="utf-8",
    )
    assert "work/pr-body-M0.1.md" in paths(repo)

    (work / "implementation-summary-M0.1.md").write_text(
        "## Summary\n\nDid the thing.\n", encoding="utf-8"
    )
    watched = paths(repo)
    assert "work/implementation-summary-M0.1.md" in watched
    assert "work/pr-body-M0.1.md" not in watched


def test_only_the_summary_section_of_a_pr_body_is_chunked(repo: Path) -> None:
    work = repo / "work"
    work.mkdir()
    (work / "pr-body-M0.1.md").write_text(
        "## Implementation summary (dev-authored)\n\nUnique prose.\n\n"
        "## Brief\n\nDuplicated inlined content.\n",
        encoding="utf-8",
    )
    info = build_node_info(repo)
    by_id = {v["id"]: v for v in info.values() if v.get("id")}

    bodies = [c.body for c in chunks_for(repo, "work/pr-body-M0.1.md", info, by_id)]

    assert bodies == ["Unique prose."]


# --- chunking ---------------------------------------------------------------


def test_a_planning_sheet_becomes_one_chunk_per_section(repo: Path) -> None:
    sheet = next(p for p in paths(repo) if p.startswith("planning/M0.1_"))
    info = build_node_info(repo)
    by_id = {v["id"]: v for v in info.values() if v.get("id")}

    chunks = chunks_for(repo, sheet, info, by_id)

    assert len(chunks) > 1
    assert all(c.kind == KIND_PLANNING and c.scope == SCOPE_LIVE for c in chunks)
    assert all(c.node_key == M01_KEY for c in chunks)
    assert all(c.node_id == "M0.1" for c in chunks)


def test_empty_sections_are_dropped(repo: Path) -> None:
    sheet = repo / "planning" / "empty_test.md"
    info = build_node_info(repo)
    by_id: dict = {}
    sheet.write_text("## Has content\n\nyes\n\n## Empty\n", encoding="utf-8")

    chunks = chunks_for(repo, "planning/empty_test.md", info, by_id)

    assert [c.heading for c in chunks] == ["Has content"]


def test_a_roadmap_chunk_yields_one_chunk_per_node(repo: Path) -> None:
    info = build_node_info(repo)
    by_id = {v["id"]: v for v in info.values() if v.get("id")}

    chunks = chunks_for(repo, "roadmap/phases/M0.json", info, by_id)

    assert {c.heading for c in chunks} == {"M0", "M0.1", "M0.3", "M2"}
    assert all(c.kind == KIND_NODE for c in chunks)


def test_node_body_flattens_the_prose_fields() -> None:
    body = node_body(
        {
            "title": "Retry queue",
            "goal": "Stop dropping payments.",
            "acceptance": ["retries thrice", "gives up cleanly"],
            "risks": ["thundering herd"],
            "notes": "See ADR 4.",
        }
    )

    for expected in ("Retry queue", "Stop dropping", "retries thrice", "thundering herd", "ADR 4"):
        assert expected in body


def test_shared_and_governance_documents_have_no_node_identity(repo: Path) -> None:
    info = build_node_info(repo)
    chunks = chunks_for(repo, "shared/api-contract.md", info, {})

    assert chunks
    assert all(c.kind == KIND_SHARED and not c.node_key for c in chunks)


# --- derived context --------------------------------------------------------


def test_context_carries_identity_status_codename_and_ancestors(repo: Path) -> None:
    info = build_node_info(repo)
    by_id = {v["id"]: v for v in info.values() if v.get("id")}

    context = derive_context(
        info[M01_KEY], kind=KIND_PLANNING, heading="Approach", doc_path="x", by_id=by_id
    )

    assert "M0.1" in context
    assert "Establish shared contracts" in context
    assert "milestone" in context and "Complete" in context
    assert "contracts-bootstrap" in context
    assert "under M0" in context  # the ancestor chain
    assert "Approach" in context


def test_context_falls_back_to_the_path_when_there_is_no_node(repo: Path) -> None:
    context = derive_context(
        None, kind=KIND_SHARED, heading="Auth", doc_path="shared/x.md", by_id={}
    )
    assert "shared/x.md" in context and "Auth" in context


def test_a_node_chunk_does_not_repeat_its_id_as_a_heading(repo: Path) -> None:
    info = build_node_info(repo)
    context = derive_context(
        info[M01_KEY], kind=KIND_NODE, heading="M0.1", doc_path="x", by_id={}
    )
    assert context.count("M0.1") == 1


# --- archived ---------------------------------------------------------------


def test_archived_sheets_are_watched_and_marked(repo: Path) -> None:
    from specy_road.archive_ops import archive_node

    archive_node(repo, "M0.1")  # already Complete in the fixture

    watched = paths(repo)
    archived_sheets = [p for p in watched if p.startswith("roadmap/archive/planning/")]
    assert archived_sheets

    info = build_node_info(repo)
    chunks = chunks_for(repo, archived_sheets[0], info, {})
    assert chunks and all(c.scope == SCOPE_ARCHIVED for c in chunks)
    assert all(c.node_id == "M0.1" for c in chunks)


def test_archived_identity_survives_the_node_leaving_the_live_graph(repo: Path) -> None:
    from specy_road.archive_ops import archive_node

    archive_node(repo, "M0.1")
    identity = build_node_info(repo)[M01_KEY]

    assert identity["scope"] == SCOPE_ARCHIVED
    assert identity["id"] == "M0.1"
    assert identity["archive_id"].startswith("M0.1-")


def test_a_deep_capsule_is_still_fully_indexable(repo: Path) -> None:
    """The deep tier stores plain JSON precisely so this keeps working."""
    from specy_road.archive_deep import deepen_archive
    from specy_road.archive_ops import archive_node

    record = archive_node(repo, "M0.1")
    deepened = deepen_archive(repo, record["archive_id"])
    capsule_rel = deepened["bundle"]["path"]

    assert capsule_rel in paths(repo)
    info = build_node_info(repo)
    chunks = chunks_for(repo, capsule_rel, info, {})

    kinds = {c.kind for c in chunks}
    assert KIND_NODE in kinds and KIND_PLANNING in kinds
    assert all(c.scope == SCOPE_ARCHIVED for c in chunks)


# --- robustness -------------------------------------------------------------


def test_an_unparseable_chunk_file_costs_only_its_own_chunks(repo: Path) -> None:
    (repo / "roadmap" / "phases" / "M0.json").write_text("{ broken", encoding="utf-8")

    chunks = all_chunks(repo)

    assert not [c for c in chunks if c.doc_path == "roadmap/phases/M0.json"]
    assert [c for c in chunks if c.kind == KIND_PLANNING]


def test_a_missing_planning_directory_is_not_an_error(tmp_path: Path) -> None:
    (tmp_path / "shared").mkdir()
    (tmp_path / "shared" / "x.md").write_text("## A\n\nbody\n", encoding="utf-8")

    assert [c.kind for c in all_chunks(tmp_path)] == [KIND_SHARED]
