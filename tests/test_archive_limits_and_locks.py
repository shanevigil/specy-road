"""Defects found by adversarial review of the archive feature line.

Each test here corresponds to a bug that shipped and was fixed. They exist so
the same mistake cannot return quietly.
"""

from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

import pytest

from specy_road.archive_ops import archive_node
from specy_road.archive_plan import plan_archive
from tests.helpers import DOGFOOD


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    dest = tmp_path / "repo"
    shutil.copytree(DOGFOOD, dest)
    return dest


def _validate(root: Path) -> None:
    from roadmap_crud_ops import run_validate_raise

    run_validate_raise(root)


def _add_phase(repo: Path, nid: str, children: int) -> None:
    """A phase plus N Complete leaves, each in its own (small) live chunk."""
    manifest = repo / "roadmap" / "manifest.json"
    doc = json.loads(manifest.read_text(encoding="utf-8"))
    pk = str(uuid.uuid5(uuid.NAMESPACE_DNS, nid))
    slug = nid.lower().replace(".", "-")
    (repo / f"planning/{nid}_{slug}_{pk}.md").write_text("# phase\n", encoding="utf-8")
    (repo / f"roadmap/phases/{nid}.json").write_text(
        json.dumps(
            {"nodes": [{
                "id": nid, "node_key": pk, "type": "phase", "title": f"Phase {nid}",
                "codename": slug, "parent_id": None,
                "status": "Complete", "sibling_order": 50, "dependencies": [],
                "planning_dir": f"planning/{nid}_{slug}_{pk}.md",
            }]}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    doc["includes"].append(f"phases/{nid}.json")
    for i in range(1, children + 1):
        cid = f"{nid}.{i}"
        k = str(uuid.uuid5(uuid.NAMESPACE_DNS, cid))
        cslug = f"t{i}-{slug}"
        (repo / f"planning/{cid}_{cslug}_{k}.md").write_text("# t\n", encoding="utf-8")
        (repo / f"roadmap/phases/{cid}.json").write_text(
            json.dumps(
                {"nodes": [{
                    "id": cid, "node_key": k, "type": "task", "title": f"Task {cid}",
                    "codename": cslug,
                    "parent_id": nid, "status": "Complete", "sibling_order": i,
                    "dependencies": [],
                    "goal": "Ship the thing described by this task.",
                    "acceptance": ["It works end to end.", "It is covered by tests."],
                    "planning_dir": f"planning/{cid}_{cslug}_{k}.md",
                }]}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        doc["includes"].append(f"phases/{cid}.json")
    manifest.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_a_large_archive_does_not_trip_the_chunk_line_limit(repo: Path) -> None:
    """Archived files are not roadmap source and must be exempt from the cap.

    `archive` writes a whole subtree into one file and the ledger grows with
    every record. Scanning those against `roadmap_json_chunk_max_lines` failed
    on exactly the repositories archiving exists to help — and the operator
    cannot split them, because the archive owns their layout. One archive of a
    31-node phase was enough to make validate, export and every CRUD command
    exit 1.
    """
    _add_phase(repo, "M9", children=30)
    _validate(repo)

    archive_node(repo, "M9")

    chunk = next((repo / "roadmap" / "archive" / "chunks").glob("*.json"))
    assert len(chunk.read_text(encoding="utf-8").splitlines()) > 500
    _validate(repo)  # must not raise


def test_archiving_an_ancestor_of_a_locked_milestone_is_refused(
    repo: Path,
) -> None:
    """The lock marks a milestone and its DESCENDANTS.

    A root-only check passed when archiving an ANCESTOR, carrying the locked
    subtree out from under an in-flight rollup branch.
    """
    chunk = repo / "roadmap" / "phases" / "M0.json"
    doc = json.loads(chunk.read_text(encoding="utf-8"))
    for n in doc["nodes"]:
        if n["id"] == "M0.1":
            n["milestone_execution"] = {
                "state": "pending_mr",
                "rollup_branch": "rollup/M0.1",
                "integration_branch": "main",
                "remote": "origin",
            }
    chunk.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    m1 = repo / "roadmap" / "phases" / "M1.json"
    d1 = json.loads(m1.read_text(encoding="utf-8"))
    for n in d1["nodes"]:
        if n["id"] == "M0.2":
            n["status"] = "Complete"
    m1.write_text(json.dumps(d1, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="milestone"):
        plan_archive(repo, "M0")


def test_archiving_the_last_live_subtree_is_refused(repo: Path) -> None:
    """An empty `includes` reads as the legacy manifest layout and cannot load."""
    from roadmap_chunk_utils import load_json_chunk, write_json_chunk

    for name in ("M0.json", "M1.json"):
        path = repo / "roadmap" / "phases" / name
        nodes = load_json_chunk(path)
        for n in nodes:
            n["status"] = "Complete"
            if n["id"] in ("M0", "M1", "M2"):
                n["parent_id"] = None
        write_json_chunk(path, nodes)

    archive_node(repo, "M0")
    archive_node(repo, "M2")

    with pytest.raises(ValueError, match="empty the roadmap"):
        plan_archive(repo, "M1")

    _validate(repo)


def test_restore_keeps_the_archive_when_validation_fails(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Deleting the only copy on the way to reporting an error is unrecoverable."""
    from specy_road.archive_index import load_archive_index
    import specy_road.archive_restore as mod

    rec = archive_node(repo, "M0.1")
    chunk = repo / rec["chunk"]
    assert chunk.is_file()

    def boom(root: Path) -> None:
        raise ValueError("validation blew up")

    monkeypatch.setattr(mod, "run_validate_raise", boom, raising=False)
    monkeypatch.setattr(
        "roadmap_crud_ops.run_validate_raise", boom, raising=False
    )

    with pytest.raises(ValueError):
        mod.restore_archive(repo, rec["archive_id"])

    assert chunk.is_file(), "archive chunk was destroyed before validation"
    assert load_archive_index(repo)["records"], "ledger record was dropped"


def test_archiving_a_node_with_an_open_claim_is_refused(repo: Path) -> None:
    """`validate` rejects a registry entry whose node_id left the graph.

    Archiving a claimed node used to apply fully and only then fail validation,
    leaving the repository failing validate with no hint why — and stranding
    the claimant's feature branch. Refused at plan time, before anything moves.
    """
    (repo / "roadmap" / "registry.yaml").write_text(
        "version: 1\n"
        "entries:\n"
        "  - codename: contracts-bootstrap\n"
        "    node_id: M0.1\n"
        "    branch: feature/rm-contracts-bootstrap\n"
        "    touch_zones: []\n"
        "    started: '2026-01-01'\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="still registered"):
        plan_archive(repo, "M0.1")

    assert not (repo / "roadmap" / "archive").exists()
    _validate(repo)
