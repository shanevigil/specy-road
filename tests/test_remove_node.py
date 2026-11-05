"""``remove-node`` eligibility, dry-run, and shared hard-remove paths (M21.4)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from specy_road.bundled_scripts.roadmap_chunk_utils import load_json_chunk, write_json_chunk
from specy_road.bundled_scripts.roadmap_load import load_roadmap
from tests.helpers import BUNDLED_SCRIPTS, script_subprocess_env
from tests.test_roadmap_crud import (
    crud_fixture_repo,
    run_crud,
    write_registry_claim,
)


def _tree_bytes(repo: Path) -> bytes:
    parts: list[bytes] = []
    for p in sorted(repo.rglob("*")):
        if p.is_file() and "schemas" not in p.parts:
            parts.append(p.read_bytes())
    return b"".join(parts)


def test_remove_node_succeeds_and_validates(tmp_path: Path) -> None:
    crud_fixture_repo(tmp_path)
    nk992 = "10000000-0000-4000-8000-000000009903"
    planning = tmp_path / "planning" / f"M99.2_two_{nk992}.md"
    r = run_crud(
        tmp_path,
        "--repo-root",
        str(tmp_path),
        "remove-node",
        "M99.2",
    )
    assert r.returncode == 0, r.stderr
    assert "[ok] removed M99.2" in r.stdout
    assert not planning.exists()
    nodes = load_json_chunk(tmp_path / "roadmap" / "phases" / "T.json")
    assert {n["id"] for n in nodes} == {"M99", "M99.1"}
    v = subprocess.run(
        [
            sys.executable,
            str(BUNDLED_SCRIPTS / "validate_roadmap.py"),
            "--repo-root",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        env=script_subprocess_env(),
    )
    assert v.returncode == 0, v.stderr


@pytest.mark.parametrize(
    ("setup", "needles"),
    [
        (
            lambda repo: None,
            ["child node M99.1 has parent_id 'M99'"],
        ),
        (
            lambda repo: write_registry_claim(
                repo, "M99.2", "two", "feature/rm-two", "Pat"
            ),
            ["registry claim codename 'two', branch 'feature/rm-two'"],
        ),
        (
            lambda repo: run_crud(
                repo,
                "--repo-root",
                str(repo),
                "edit-node",
                "M99.2",
                "--set",
                "status=Complete",
            ),
            ["status is 'Complete', not 'Not Started'"],
        ),
        (
            lambda repo: None,
            ["node M99.2 depends on node_key of 'M99.1'"],
        ),
    ],
    ids=["child", "registry-claim", "started-status", "dependent"],
)
def test_remove_node_lists_each_blocker(
    tmp_path: Path, setup: object, needles: list[str]
) -> None:
    crud_fixture_repo(tmp_path)
    if "child node" in needles[0]:
        target = "M99"
    elif "depends on node_key" in needles[0]:
        target = "M99.1"
    else:
        target = "M99.2"
    setup(tmp_path)
    r = run_crud(
        tmp_path,
        "--repo-root",
        str(tmp_path),
        "remove-node",
        target,
    )
    assert r.returncode == 1
    err = r.stderr
    for needle in needles:
        assert needle in err
    nodes = load_roadmap(tmp_path)["nodes"]
    assert any(n["id"] == target for n in nodes)


def test_remove_node_lists_every_blocker_together(tmp_path: Path) -> None:
    crud_fixture_repo(tmp_path)
    write_registry_claim(tmp_path, "M99", "phase", "feature/rm-phase", "Pat")
    run_crud(
        tmp_path,
        "--repo-root",
        str(tmp_path),
        "edit-node",
        "M99",
        "--set",
        "status=In Progress",
    )
    r = run_crud(
        tmp_path,
        "--repo-root",
        str(tmp_path),
        "remove-node",
        "M99",
    )
    assert r.returncode == 1
    err = r.stderr
    assert "child node M99.1" in err
    assert "registry claim codename 'phase'" in err
    assert "status is 'In Progress'" in err


def test_remove_node_dry_run_eligible_writes_nothing(tmp_path: Path, capsys) -> None:
    crud_fixture_repo(tmp_path)
    before = _tree_bytes(tmp_path)
    r = run_crud(
        tmp_path,
        "--repo-root",
        str(tmp_path),
        "remove-node",
        "M99.2",
        "--dry-run",
    )
    assert r.returncode == 0, r.stderr
    assert "would remove node M99.2" in r.stdout
    assert "planning sheet: planning/" in r.stdout
    assert _tree_bytes(tmp_path) == before
    assert any(n["id"] == "M99.2" for n in load_roadmap(tmp_path)["nodes"])


def test_remove_node_dry_run_blocked_writes_nothing(tmp_path: Path) -> None:
    crud_fixture_repo(tmp_path)
    before = _tree_bytes(tmp_path)
    r = run_crud(
        tmp_path,
        "--repo-root",
        str(tmp_path),
        "remove-node",
        "M99",
        "--dry-run",
    )
    assert r.returncode == 1
    assert "child node" in r.stderr
    assert _tree_bytes(tmp_path) == before


@pytest.mark.parametrize("dry_run", [False, True], ids=["real", "dry-run"])
def test_refused_removal_preserves_every_byte_when_post_graph_invalid(
    tmp_path: Path, dry_run: bool
) -> None:
    """Real removal and dry-run both validate the post-delete graph; refusal changes nothing."""
    crud_fixture_repo(tmp_path)
    chunk = tmp_path / "roadmap" / "phases" / "T.json"
    nodes = load_json_chunk(chunk)
    next(n for n in nodes if n["id"] == "M99.1")["type"] = "invalid"
    write_json_chunk(chunk, nodes)
    before = _tree_bytes(tmp_path)
    argv = ["--repo-root", str(tmp_path), "remove-node", "M99.2"]
    if dry_run:
        argv.append("--dry-run")
    r = run_crud(tmp_path, *argv)
    assert r.returncode == 1
    assert _tree_bytes(tmp_path) == before


@pytest.mark.parametrize("dry_run", [False, True], ids=["real", "dry-run"])
def test_refused_removal_leaves_healable_bytes_untouched(tmp_path: Path, dry_run: bool) -> None:
    crud_fixture_repo(tmp_path)
    chunk = tmp_path / "roadmap" / "phases" / "T.json"
    nodes = load_json_chunk(chunk)
    next(n for n in nodes if n["id"] == "M99")["parallel_tracks"] = 0
    leaf = next(n for n in nodes if n["id"] == "M99.2")
    del leaf["codename"]
    write_json_chunk(chunk, nodes)
    before = _tree_bytes(tmp_path)
    argv = ["--repo-root", str(tmp_path), "remove-node", "M99.2"]
    if dry_run:
        argv.append("--dry-run")
    r = run_crud(tmp_path, *argv)
    assert r.returncode == 1
    assert _tree_bytes(tmp_path) == before


def test_refused_remove_node_on_blockers_preserves_tree(tmp_path: Path) -> None:
    crud_fixture_repo(tmp_path)
    before = _tree_bytes(tmp_path)
    r = run_crud(
        tmp_path,
        "--repo-root",
        str(tmp_path),
        "remove-node",
        "M99",
    )
    assert r.returncode == 1
    assert "child node" in r.stderr
    assert _tree_bytes(tmp_path) == before


def test_dry_run_succeeds_when_manifest_chunk_is_an_in_repo_symlink(tmp_path: Path) -> None:
    crud_fixture_repo(tmp_path)
    chunk = tmp_path / "roadmap" / "phases" / "T.json"
    storage = tmp_path / "roadmap" / "T-storage.json"
    storage.write_bytes(chunk.read_bytes())
    chunk.unlink()
    chunk.symlink_to(storage.resolve())
    before = _tree_bytes(tmp_path)
    r = run_crud(
        tmp_path,
        "--repo-root",
        str(tmp_path),
        "remove-node",
        "M99.2",
        "--dry-run",
    )
    assert r.returncode == 0, r.stderr + r.stdout
    assert "would remove node M99.2" in r.stdout
    assert _tree_bytes(tmp_path) == before
    assert any(n["id"] == "M99.2" for n in load_roadmap(tmp_path)["nodes"])


def test_archive_hard_remove_refuses_registry_claim(tmp_path: Path) -> None:
    crud_fixture_repo(tmp_path)
    write_registry_claim(tmp_path, "M99.2", "two", "feature/rm-two", "Pat")
    r = run_crud(
        tmp_path,
        "--repo-root",
        str(tmp_path),
        "archive-node",
        "M99.2",
        "--hard-remove",
    )
    assert r.returncode == 1
    assert "registry claim" in r.stderr


def test_gui_delete_refuses_a_claimed_leaf(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    crud_fixture_repo(tmp_path)
    write_registry_claim(tmp_path, "M99.2", "two", "feature/rm-two", "Pat")
    monkeypatch.setenv("SPECY_ROAD_REPO_ROOT", str(tmp_path))
    from specy_road.gui_app import create_app

    client = TestClient(create_app())
    fp = client.get("/api/roadmap").json()["fingerprint"]
    r = client.delete(
        "/api/nodes/M99.2",
        headers={"X-PM-Gui-Fingerprint": str(fp)},
    )
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert isinstance(detail, str)
    assert "registry claim" in detail
