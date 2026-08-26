"""Deep archive: bundle a shallow archive away, leave a reference, restore it.

The bundle is the only copy of the archived nodes once deepening finishes, so
the checksum guard and the "index record survives" property are the two things
worth pinning hardest.
"""

from __future__ import annotations

import json
import shutil
import tarfile
from pathlib import Path

import pytest

from specy_road.archive_deep import deepen_archive, undeepen_archive
from specy_road.archive_index import (
    archive_refs_dir,
    archived_node_keys,
    find_record,
    load_archive_index,
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


def test_deepening_replaces_loose_files_with_one_bundle(repo: Path) -> None:
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


def test_the_bundle_carries_the_chunk_and_the_planning_sheet(repo: Path) -> None:
    rec = archive_node(repo, "M0.1")
    deepened = deepen_archive(repo, rec["archive_id"])

    with tarfile.open(repo / deepened["bundle"]["path"]) as tar:
        names = tar.getnames()
    assert any(n.startswith("chunk/") and n.endswith(".json") for n in names)
    assert any(n.startswith("planning/") and n.endswith(".md") for n in names)


def test_the_reference_file_stands_alone(repo: Path, deep: str) -> None:
    """It must answer "what was this, where did it land?" without the bundle."""
    ref = json.loads(
        (archive_refs_dir(repo) / f"{deep}.json").read_text(encoding="utf-8")
    )
    assert ref["archive_id"] == deep
    assert ref["root_node_id"] == "M0.1"
    assert [n["id"] for n in ref["nodes"]] == ["M0.1"]
    assert "git" in ref and "bundle" in ref
    assert deep in ref["note"]


def test_archived_dependencies_survive_deepening(repo: Path, deep: str) -> None:
    """The ledger has to keep working when the nodes are inside a tarball."""
    from roadmap_load import load_roadmap
    from validate_roadmap_checks import validate_dependency_ids

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


def test_a_tampered_bundle_is_refused_before_anything_unpacks(
    repo: Path, deep: str
) -> None:
    """Restoring silently-altered roadmap nodes is worse than refusing."""
    rec = find_record(load_archive_index(repo), deep)
    bundle = repo / rec["bundle"]["path"]
    bundle.write_bytes(bundle.read_bytes() + b"tampered")

    with pytest.raises(ValueError, match="failed its checksum"):
        undeepen_archive(repo, deep)

    assert find_record(load_archive_index(repo), deep)["depth"] == "deep"


def test_a_missing_bundle_is_reported_clearly(repo: Path, deep: str) -> None:
    rec = find_record(load_archive_index(repo), deep)
    (repo / rec["bundle"]["path"]).unlink()

    with pytest.raises(ValueError, match="which is missing"):
        undeepen_archive(repo, deep)


def test_restore_from_deep_is_one_step_and_byte_identical(repo: Path) -> None:
    """`restore-archive` on a deep archive unpacks and restores in one go."""
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
