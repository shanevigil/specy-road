"""Deep archive: fold a shallow archive away, leave a reference, restore it.

The capsule is the only copy of the archived nodes once deepening finishes, so
the checksum guard and the "index record survives" property are the two things
worth pinning hardest. The capsule being *text* is the third: it is what keeps
archived work greppable and cheap for git to store, and it is what makes the
recorded ``sha256`` reproducible.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from specy_road.archive_deep import deepen_archive, undeepen_archive
from specy_road.archive_index import (
    archive_refs_dir,
    archived_node_keys,
    find_record,
    load_archive_index,
    write_archive_index,
)
from specy_road.archive_ops import archive_node
from specy_road.archive_restore import restore_archive
from tests.helpers import DOGFOOD

M01_KEY = "44ef4a9d-923f-545c-8187-eaabc7ca86ba"


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    dest = tmp_path / "repo"
    shutil.copytree(DOGFOOD, dest)
    return dest


@pytest.fixture()
def deep(repo: Path) -> str:
    """A deep-archived M0.1, returning its archive id."""
    rec = archive_node(repo, "M0.1")
    deepen_archive(repo, rec["archive_id"])
    return rec["archive_id"]


def _snapshot(repo: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for sub in ("roadmap", "planning"):
        for p in sorted((repo / sub).rglob("*")):
            if p.is_file() and "archive" not in p.relative_to(repo).parts:
                out[str(p.relative_to(repo))] = p.read_text(encoding="utf-8")
    return out


def test_deepening_replaces_loose_files_with_one_capsule(repo: Path) -> None:
    rec = archive_node(repo, "M0.1")
    chunk = repo / rec["chunk"]
    sheet = repo / rec["planning"][0]["stored"]
    assert chunk.is_file() and sheet.is_file()

    deepened = deepen_archive(repo, rec["archive_id"])

    assert deepened["depth"] == "deep"
    assert deepened["chunk"] is None
    assert deepened["planning"] == []
    assert not chunk.exists()
    assert not sheet.exists()
    assert (repo / deepened["bundle"]["path"]).is_file()
    assert deepened["bundle"]["path"].endswith(".json")


def test_the_capsule_carries_the_chunk_and_the_planning_sheet(repo: Path) -> None:
    rec = archive_node(repo, "M0.1")
    deepened = deepen_archive(repo, rec["archive_id"])

    capsule = json.loads(
        (repo / deepened["bundle"]["path"]).read_text(encoding="utf-8")
    )
    assert capsule["capsule_version"] == 1
    assert capsule["archive_id"] == rec["archive_id"]
    assert [n["id"] for n in capsule["nodes"]] == ["M0.1"]
    assert capsule["planning"][0]["origin"].startswith("planning/")
    assert capsule["planning"][0]["body"].strip()


def test_the_capsule_is_greppable_text(repo: Path, deep: str) -> None:
    """The whole point of not compressing: a human or agent can still read it."""
    rec = find_record(load_archive_index(repo), deep)
    text = (repo / rec["bundle"]["path"]).read_text(encoding="utf-8")

    title = rec["nodes_summary"][0]["title"]
    assert title in text
    assert M01_KEY in text


def test_deepening_is_byte_reproducible(repo: Path) -> None:
    """Same content in, same capsule out — including the recorded checksum.

    A gzipped tarball could not pass this: Python stamps the current time into
    the gzip header and per-file mtime/uid/gid into the tar headers, so every
    re-bundle produced a different blob for identical content.
    """
    rec = archive_node(repo, "M0.1")
    aid = rec["archive_id"]

    first = deepen_archive(repo, aid)
    first_bytes = (repo / first["bundle"]["path"]).read_bytes()
    first_sha = first["bundle"]["sha256"]

    undeepen_archive(repo, aid)
    second = deepen_archive(repo, aid)

    assert (repo / second["bundle"]["path"]).read_bytes() == first_bytes
    assert second["bundle"]["sha256"] == first_sha


def test_the_reference_file_stands_alone(repo: Path, deep: str) -> None:
    """It must answer "what was this, where did it land?" without the capsule."""
    ref = json.loads(
        (archive_refs_dir(repo) / f"{deep}.json").read_text(encoding="utf-8")
    )
    assert ref["archive_id"] == deep
    assert ref["root_node_id"] == "M0.1"
    assert [n["id"] for n in ref["nodes"]] == ["M0.1"]
    assert "git" in ref and "bundle" in ref
    assert deep in ref["note"]


def test_archived_dependencies_survive_deepening(repo: Path, deep: str) -> None:
    """The ledger has to keep working when the nodes are inside a capsule."""
    from specy_road.bundled_scripts.roadmap_load import load_roadmap
    from specy_road.bundled_scripts.validate_roadmap_checks import validate_dependency_ids

    assert M01_KEY in archived_node_keys(repo)
    validate_dependency_ids(load_roadmap(repo)["nodes"], repo)


def test_a_deep_archive_is_still_listable(repo: Path, deep: str) -> None:
    rec = find_record(load_archive_index(repo), deep)
    assert rec["depth"] == "deep"
    assert [n["id"] for n in rec["nodes_summary"]] == ["M0.1"]


def test_deepening_twice_is_refused(repo: Path, deep: str) -> None:
    with pytest.raises(ValueError, match="already deep-archived"):
        deepen_archive(repo, deep)


def test_undeepen_returns_it_to_the_shallow_tier(repo: Path, deep: str) -> None:
    rec = undeepen_archive(repo, deep)

    assert rec["depth"] == "shallow"
    assert rec["bundle"] is None
    assert (repo / rec["chunk"]).is_file()
    assert (repo / rec["planning"][0]["stored"]).is_file()
    assert not (archive_refs_dir(repo) / f"{deep}.json").exists()


def test_undeepen_puts_sheets_back_at_their_recorded_origin(repo: Path) -> None:
    """The capsule carries ``origin`` so restore never guesses from a filename."""
    rec = archive_node(repo, "M0.1")
    origin = rec["planning"][0]["origin"]
    deepen_archive(repo, rec["archive_id"])

    restored = undeepen_archive(repo, rec["archive_id"])

    assert restored["planning"][0]["origin"] == origin


def test_a_tampered_capsule_is_refused_before_anything_unfolds(
    repo: Path, deep: str
) -> None:
    """Restoring silently-altered roadmap nodes is worse than refusing."""
    rec = find_record(load_archive_index(repo), deep)
    capsule = repo / rec["bundle"]["path"]
    capsule.write_bytes(capsule.read_bytes() + b"tampered")

    with pytest.raises(ValueError, match="failed its checksum"):
        undeepen_archive(repo, deep)

    assert find_record(load_archive_index(repo), deep)["depth"] == "deep"


def test_a_missing_capsule_is_reported_clearly(repo: Path, deep: str) -> None:
    rec = find_record(load_archive_index(repo), deep)
    (repo / rec["bundle"]["path"]).unlink()

    with pytest.raises(ValueError, match="which is missing"):
        undeepen_archive(repo, deep)


def test_a_pre_release_tar_bundle_is_reported_by_name(repo: Path, deep: str) -> None:
    """The tar format never shipped, so no reader is kept — but say so plainly."""
    doc = load_archive_index(repo)
    rec = find_record(doc, deep)
    rec["bundle"] = {"path": f"roadmap/archive/deep/{deep}.tar.gz", "sha256": "0" * 64}
    write_archive_index(repo, doc)

    with pytest.raises(ValueError, match="pre-release tar deep-archive format"):
        undeepen_archive(repo, deep)


def test_restore_from_deep_is_one_step_and_byte_identical(repo: Path) -> None:
    """`restore-archive` on a deep archive unfolds and restores in one go."""
    before = _snapshot(repo)
    rec = archive_node(repo, "M0.1")
    deepen_archive(repo, rec["archive_id"])

    restore_archive(repo, rec["archive_id"])

    assert _snapshot(repo) == before
    assert load_archive_index(repo)["records"] == []
    assert archived_node_keys(repo) == set()


def test_undeepen_on_a_shallow_archive_is_refused(repo: Path) -> None:
    rec = archive_node(repo, "M0.1")
    with pytest.raises(ValueError, match="not deep-archived"):
        undeepen_archive(repo, rec["archive_id"])
