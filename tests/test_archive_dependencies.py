"""A live node may keep depending on archived work.

`validate_dependency_ids` hard-fails on a dependency whose node_key is not in
the merged graph. Archiving a completed milestone that live nodes depend on
would trip exactly that check, so the archive index doubles as a ledger of
satisfied keys: archived implies Complete implies the edge is met.

That is what lets archiving leave every live node's `dependencies` untouched,
which in turn is what makes restore lossless. These tests pin both halves.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from validate_roadmap_checks import validate_dependency_ids

from specy_road.archive_index import archive_index_path, archived_node_keys
from specy_road.archive_ops import archive_node
from specy_road.archive_restore import restore_archive
from tests.helpers import DOGFOOD

# M1 (live phase) depends on M0.1's node_key in the dogfood fixture.
M01_KEY = "44ef4a9d-923f-545c-8187-eaabc7ca86ba"


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    dest = tmp_path / "repo"
    shutil.copytree(DOGFOOD, dest)
    return dest


def _live_nodes(repo: Path) -> list[dict]:
    from roadmap_load import load_roadmap

    return load_roadmap(repo)["nodes"]


def _dependencies_of(repo: Path, node_id: str) -> list[str]:
    for n in _live_nodes(repo):
        if n["id"] == node_id:
            return list(n.get("dependencies") or [])
    raise AssertionError(f"{node_id} not in the live graph")


def test_archiving_records_every_key_in_the_subtree(repo: Path) -> None:
    assert archived_node_keys(repo) == set()
    archive_node(repo, "M0.1")
    assert M01_KEY in archived_node_keys(repo)


def test_a_live_dependency_on_archived_work_still_validates(repo: Path) -> None:
    archive_node(repo, "M0.1")

    nodes = _live_nodes(repo)
    assert M01_KEY not in {n["node_key"] for n in nodes}
    assert M01_KEY in _dependencies_of(repo, "M1")

    validate_dependency_ids(nodes, repo)  # must not raise


def test_the_dependency_edge_survives_the_round_trip_untouched(repo: Path) -> None:
    before = _dependencies_of(repo, "M1")
    rec = archive_node(repo, "M0.1")
    assert _dependencies_of(repo, "M1") == before

    restore_archive(repo, rec["archive_id"])
    assert _dependencies_of(repo, "M1") == before
    assert archived_node_keys(repo) == set()


def test_a_dangling_dependency_is_still_rejected(repo: Path) -> None:
    """The archive escape hatch must not blanket-accept unknown keys."""
    nodes = _live_nodes(repo)
    for n in nodes:
        if n["id"] == "M1":
            n["dependencies"] = ["00000000-0000-0000-0000-000000000000"]

    with pytest.raises(SystemExit):
        validate_dependency_ids(nodes, repo)


def test_losing_the_index_fails_loudly_rather_than_silently(repo: Path) -> None:
    """The index is the only thing keeping archived edges resolvable.

    If it is deleted, the dependency genuinely cannot be verified any more, so
    validate must say so rather than quietly accepting or quietly dropping it.
    """
    archive_node(repo, "M0.1")
    archive_index_path(repo).unlink()

    with pytest.raises(SystemExit):
        validate_dependency_ids(_live_nodes(repo), repo)


def test_a_corrupt_index_raises_instead_of_starting_over(repo: Path) -> None:
    """Silently treating a malformed ledger as empty would strand every edge."""
    archive_node(repo, "M0.1")
    archive_index_path(repo).write_text("{not json", encoding="utf-8")

    with pytest.raises(ValueError, match="not valid JSON"):
        archived_node_keys(repo)


def test_a_schema_invalid_index_is_rejected(repo: Path) -> None:
    archive_node(repo, "M0.1")
    path = archive_index_path(repo)
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["records"][0]["depth"] = "medium"
    path.write_text(json.dumps(doc), encoding="utf-8")

    with pytest.raises(ValueError, match="archive index invalid"):
        archived_node_keys(repo)


def test_no_index_means_no_archived_keys(repo: Path) -> None:
    """A repo that has never archived must not pay for the feature."""
    assert archived_node_keys(repo) == set()
    validate_dependency_ids(_live_nodes(repo), repo)
