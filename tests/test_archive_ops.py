"""Archiving a completed subtree moves it out of the live graph, reversibly.

The awkward shapes are the point of these tests: a subtree that shares its
chunk with live nodes, one spread across several chunks, and one that owns its
chunk outright. All three must round-trip back to a byte-identical tree.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from specy_road.archive_index import load_archive_index
from specy_road.archive_ops import archive_node
from specy_road.archive_plan import plan_archive
from specy_road.archive_restore import restore_archive
from tests.helpers import DOGFOOD


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    dest = tmp_path / "repo"
    shutil.copytree(DOGFOOD, dest)
    return dest


def _chunk(repo: Path, name: str) -> list[dict]:
    p = repo / "roadmap" / "phases" / name
    return json.loads(p.read_text(encoding="utf-8"))["nodes"] if p.is_file() else []


def _ids(repo: Path, name: str) -> list[str]:
    return [n["id"] for n in _chunk(repo, name)]


def _includes(repo: Path) -> list[str]:
    doc = json.loads((repo / "roadmap" / "manifest.json").read_text(encoding="utf-8"))
    return list(doc.get("includes") or [])


def _set_status(repo: Path, chunk: str, node_id: str, status: str) -> None:
    p = repo / "roadmap" / "phases" / chunk
    doc = json.loads(p.read_text(encoding="utf-8"))
    for n in doc["nodes"]:
        if n["id"] == node_id:
            n["status"] = status
    p.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _snapshot(repo: Path) -> dict[str, str]:
    """Every tracked roadmap/planning file's text, keyed by repo-relative path."""
    out: dict[str, str] = {}
    for sub in ("roadmap", "planning"):
        for p in sorted((repo / sub).rglob("*")):
            if p.is_file() and "archive" not in p.relative_to(repo).parts:
                out[str(p.relative_to(repo))] = p.read_text(encoding="utf-8")
    return out


def test_refuses_a_subtree_that_is_not_complete(repo: Path) -> None:
    with pytest.raises(ValueError, match="not 'Complete'"):
        plan_archive(repo, "M0.2")


def test_force_overrides_the_completeness_gate(repo: Path) -> None:
    plan = plan_archive(repo, "M0.2", force=True)
    assert plan.node_ids == ["M0.2"]


def test_unknown_node_id_is_rejected(repo: Path) -> None:
    with pytest.raises(ValueError, match="no roadmap node with id"):
        plan_archive(repo, "M99")


def test_archiving_a_shared_chunk_leaves_live_nodes_in_place(repo: Path) -> None:
    """M0.1 is Complete but shares phases/M0.json with M0, M0.3 and M2."""
    archive_node(repo, "M0.1")
    assert _ids(repo, "M0.json") == ["M0", "M0.3", "M2"]
    assert "phases/M0.json" in _includes(repo)


def test_archiving_spans_every_chunk_the_subtree_touches(repo: Path) -> None:
    """M0's subtree is split across M0.json (M0, M0.1, M0.3) and M1.json (M0.2)."""
    _set_status(repo, "M1.json", "M0.2", "Complete")
    rec = archive_node(repo, "M0")

    assert sorted(n["id"] for n in rec["nodes_summary"]) == ["M0", "M0.1", "M0.2", "M0.3"]
    assert _ids(repo, "M0.json") == ["M2"]
    assert _ids(repo, "M1.json") == ["M1"]


def test_a_chunk_emptied_by_the_archive_is_deleted_and_deincluded(repo: Path) -> None:
    """A chunk holding nothing but archived nodes must leave `includes` too.

    Leaving the include behind while deleting the file makes the whole roadmap
    fail to load, so the two have to move together.
    """
    _move_node(repo, "M1.json", "M0.json", "M0.2")
    _set_status(repo, "M1.json", "M1", "Complete")
    archive_node(repo, "M1")

    assert not (repo / "roadmap" / "phases" / "M1.json").exists()
    assert _includes(repo) == ["phases/M0.json"]


def _move_node(repo: Path, src: str, dst: str, node_id: str) -> None:
    base = repo / "roadmap" / "phases"
    s = json.loads((base / src).read_text(encoding="utf-8"))
    d = json.loads((base / dst).read_text(encoding="utf-8"))
    moved = [n for n in s["nodes"] if n["id"] == node_id]
    s["nodes"] = [n for n in s["nodes"] if n["id"] != node_id]
    d["nodes"].extend(moved)
    (base / src).write_text(json.dumps(s, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (base / dst).write_text(json.dumps(d, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_planning_sheets_move_out_of_the_flat_planning_dir(repo: Path) -> None:
    """`validate` forbids subdirectories under planning/, so sheets park in the archive."""
    rec = archive_node(repo, "M0.1")

    moves = rec["planning"]
    assert len(moves) == 1
    assert not (repo / moves[0]["origin"]).exists()
    assert (repo / moves[0]["stored"]).is_file()
    assert moves[0]["stored"].startswith("roadmap/archive/planning/")
    assert not any(p.is_dir() for p in (repo / "planning").iterdir())


@pytest.mark.parametrize(
    "prepare,node_id",
    [
        (lambda repo: None, "M0.1"),
        (lambda repo: _set_status(repo, "M1.json", "M0.2", "Complete"), "M0"),
    ],
    ids=["shared-chunk", "multi-chunk"],
)
def test_round_trip_restores_a_byte_identical_tree(repo: Path, prepare, node_id) -> None:
    """Restore replays each node's recorded chunk and index, not just its content.

    Appending instead would reshuffle the chunk and churn the diff every time an
    archive round-trips — noise that lands in a PR.
    """
    prepare(repo)
    before = _snapshot(repo)

    rec = archive_node(repo, node_id)
    assert _snapshot(repo) != before

    restore_archive(repo, rec["archive_id"])
    assert _snapshot(repo) == before
    assert load_archive_index(repo)["records"] == []


def test_restore_rejects_an_unknown_archive_id(repo: Path) -> None:
    with pytest.raises(ValueError, match="no archive with id"):
        restore_archive(repo, "nope-00000000-20260101")


def test_archive_ids_do_not_collide_with_a_live_record(repo: Path) -> None:
    """The id embeds only node id, key prefix and date, so it can repeat.

    A restored archive frees its id again, which is fine — but while a record
    still holds one, the next archive has to step around it or the two would
    share a chunk filename.
    """
    from specy_road.archive_index import write_archive_index
    from specy_road.archive_plan import build_archive_id, unique_archive_id, utc_now_iso

    node = {"id": "M0.1", "node_key": "44ef4a9d-923f-545c-8187-eaabc7ca86ba"}
    base = build_archive_id(node, utc_now_iso())
    assert unique_archive_id(repo, base) == base

    record = archive_node(repo, "M0.1")
    doc = load_archive_index(repo)
    doc["records"][0]["archive_id"] = base
    write_archive_index(repo, doc)

    assert record["archive_id"] == base
    assert unique_archive_id(repo, base) == f"{base}-2"


def test_archive_then_restore_leaves_no_trace(repo: Path) -> None:
    """A change of mind should be net-zero, not a stray empty ledger.

    Otherwise the user is left with a file to explain in review — and, once
    committed, a tracked file that no longer records anything.
    """
    before = _snapshot(repo)
    rec = archive_node(repo, "M0.1")
    assert (repo / "roadmap" / "archive").exists()

    restore_archive(repo, rec["archive_id"])

    assert not (repo / "roadmap" / "archive").exists()
    assert _snapshot(repo) == before


def test_pruning_keeps_the_ledger_while_any_record_remains(repo: Path) -> None:
    first = archive_node(repo, "M0.1")
    archive_node(repo, "M0.3")

    restore_archive(repo, first["archive_id"])

    assert (repo / "roadmap" / "archive" / "index.json").is_file()
    assert len(load_archive_index(repo)["records"]) == 1
