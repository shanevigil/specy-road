"""M11.17: edit-node / add-node name chunk files and list paths to commit."""

from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace

from specy_road.bundled_scripts.roadmap_chunk_router_pick import simulate_chunk_lines
from specy_road.bundled_scripts.roadmap_chunk_utils import load_json_chunk, write_json_chunk
from specy_road.bundled_scripts.roadmap_crud_ops import cmd_edit
from tests.review_repo_helpers import make_review_repo
from tests.test_roadmap_crud import _edit, crud_fixture_repo, run_crud
from tests.test_roadmap_chunk_router import _milestone, _phase_M0, _seed_repo


def _commit_files(stdout: str) -> list[str]:
    m = re.search(r"^commit these files: (.+)$", stdout, re.MULTILINE)
    assert m, stdout
    return [p.strip() for p in m.group(1).split(",")]


def _roadmap_planning_bytes(root: Path) -> dict[str, bytes]:
    out: dict[str, bytes] = {}
    for prefix in ("roadmap", "planning"):
        base = root / prefix
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if path.is_file():
                out[path.relative_to(root).as_posix()] = path.read_bytes()
    return out


def _paths_changed(before: dict[str, bytes], after: dict[str, bytes]) -> set[str]:
    keys = set(before) | set(after)
    return {k for k in keys if before.get(k) != after.get(k)}


def test_edit_node_in_place_lists_read_and_written_chunk(tmp_path: Path) -> None:
    crud_fixture_repo(tmp_path)
    chunk_rel = "roadmap/phases/T.json"
    r = _edit(tmp_path, "--set", "status=Complete")
    assert r.returncode == 0, r.stderr
    assert f"read from {chunk_rel}" in r.stdout
    assert f"wrote {chunk_rel}" in r.stdout
    committed = _commit_files(r.stdout)
    assert committed == [chunk_rel]
    assert (tmp_path / chunk_rel).is_file()
    nodes = load_json_chunk(tmp_path / chunk_rel)
    assert next(n for n in nodes if n["id"] == "M99.1")["status"] == "Complete"


def test_edit_node_relocation_lists_source_dest_and_manifest(tmp_path: Path) -> None:
    nodes = [_phase_M0()] + [_milestone(f"M0.{i}", "M0", n_index=10 + i) for i in range(1, 6)]
    _seed_repo(tmp_path, {"phases/M0.json": nodes})
    chunk = tmp_path / "roadmap" / "phases" / "M0.json"
    (tmp_path / "constraints" / "file-limits.yaml").write_text(
        "roadmap_json_chunk_max_lines: 80\n", encoding="utf-8"
    )
    edited_id = "M0.5"
    r = run_crud(
        tmp_path,
        "--repo-root",
        str(tmp_path),
        "edit-node",
        edited_id,
        "--set",
        f"notes={'x' * 1000}",
    )
    assert r.returncode == 0, r.stderr
    source_rel = "roadmap/phases/M0.json"
    assert f"read from {source_rel}" in r.stdout
    assert "moved from" in r.stdout and " to " in r.stdout
    assert source_rel in r.stdout
    committed = _commit_files(r.stdout)
    assert source_rel in committed
    assert "roadmap/manifest.json" in committed
    dest_rels = [p for p in committed if p != source_rel and p != "roadmap/manifest.json"]
    assert len(dest_rels) == 1
    dest_rel = dest_rels[0]
    assert (tmp_path / dest_rel).is_file()
    assert all(n["id"] != edited_id for n in load_json_chunk(chunk))
    assert any(n["id"] == edited_id for n in load_json_chunk(tmp_path / dest_rel))


def test_add_node_lists_written_chunk_and_planning_sheet(tmp_path: Path) -> None:
    crud_fixture_repo(tmp_path)
    r = run_crud(
        tmp_path,
        "--repo-root",
        str(tmp_path),
        "add-node",
        "--chunk",
        "phases/T.json",
        "--id",
        "M99.3",
        "--type",
        "task",
        "--title",
        "Three",
        "--parent-id",
        "M99",
        "--codename",
        "three",
    )
    assert r.returncode == 0, r.stderr
    chunk_rel = "roadmap/phases/T.json"
    assert f"wrote {chunk_rel}," in r.stdout or f"wrote {chunk_rel} " in r.stdout
    committed = _commit_files(r.stdout)
    assert chunk_rel in committed
    planning = next(p for p in committed if p.startswith("planning/"))
    assert (tmp_path / planning).is_file()
    assert any(n["id"] == "M99.3" for n in load_json_chunk(tmp_path / chunk_rel))


def test_add_node_new_chunk_includes_manifest(tmp_path: Path) -> None:
    crud_fixture_repo(tmp_path)
    cur = load_json_chunk(tmp_path / "roadmap" / "phases" / "T.json")
    cap = simulate_chunk_lines(cur) + 5
    (tmp_path / "constraints" / "file-limits.yaml").write_text(
        f"roadmap_json_chunk_max_lines: {cap}\n", encoding="utf-8"
    )
    r = run_crud(
        tmp_path,
        "--repo-root",
        str(tmp_path),
        "add-node",
        "--id",
        "M99.5",
        "--type",
        "task",
        "--title",
        "Overflow",
        "--parent-id",
        "M99",
    )
    assert r.returncode == 0, r.stderr
    committed = _commit_files(r.stdout)
    assert "roadmap/manifest.json" in committed
    chunk_paths = [p for p in committed if p.startswith("roadmap/phases/") and p.endswith(".json")]
    assert len(chunk_paths) == 1
    assert chunk_paths[0] != "roadmap/phases/T.json"
    assert (tmp_path / chunk_paths[0]).is_file()
    manifest = json.loads((tmp_path / "roadmap" / "manifest.json").read_text(encoding="utf-8"))
    assert chunk_paths[0].removeprefix("roadmap/") in manifest["includes"]


def test_edit_node_planning_rename_commit_list_matches_disk(tmp_path: Path) -> None:
    crud_fixture_repo(tmp_path)
    assert _edit(tmp_path, "--set", "status=Complete").returncode == 0
    before = _roadmap_planning_bytes(tmp_path)
    r = _edit(tmp_path, "--set", "codename=renamed-one")
    assert r.returncode == 0, r.stderr
    after = _roadmap_planning_bytes(tmp_path)
    changed = _paths_changed(before, after)
    committed = set(_commit_files(r.stdout))
    assert committed == changed
    assert any(p.startswith("planning/M99.1_renamed-one_") for p in committed)
    assert any(p.startswith("planning/M99.1_one_") for p in committed)


def test_edit_node_claim_touch_zones_commit_list_includes_registry(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path)
    before = _roadmap_planning_bytes(repo)
    cmd_edit(
        SimpleNamespace(
            repo_root=str(repo),
            node_id="M1.1",
            set=["touch_zones=lib"],
            sync_codename=False,
        )
    )
    after = _roadmap_planning_bytes(repo)
    changed = _paths_changed(before, after)
    committed = set(_commit_files(capsys.readouterr().out))
    assert committed == changed
    assert "roadmap/registry.yaml" in committed
    assert "roadmap/phases/M1.json" in committed


def test_edit_node_without_zone_change_omits_registry_from_commit_list(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path)
    before = _roadmap_planning_bytes(repo)
    cmd_edit(
        SimpleNamespace(
            repo_root=str(repo),
            node_id="M1.1",
            set=["title=Renamed thing"],
            sync_codename=False,
        )
    )
    after = _roadmap_planning_bytes(repo)
    committed = set(_commit_files(capsys.readouterr().out))
    assert "roadmap/registry.yaml" not in committed
    assert committed == _paths_changed(before, after)


def test_edit_node_heal_in_another_chunk_is_in_commit_list(tmp_path: Path) -> None:
    crud_fixture_repo(tmp_path)
    t_rel = "roadmap/phases/T.json"
    u_rel = "roadmap/phases/U.json"
    nodes = load_json_chunk(tmp_path / t_rel)
    moved = next(n for n in nodes if n["id"] == "M99.2")
    moved["execution_subtask"] = "legacy"
    write_json_chunk(tmp_path / t_rel, [n for n in nodes if n["id"] != "M99.2"])
    write_json_chunk(tmp_path / u_rel, [moved])
    manifest = tmp_path / "roadmap" / "manifest.json"
    manifest.write_text(
        json.dumps({"version": 1, "includes": ["phases/T.json", "phases/U.json"]}) + "\n",
        encoding="utf-8",
    )
    before = _roadmap_planning_bytes(tmp_path)
    r = _edit(tmp_path, "--set", "status=Complete")
    assert r.returncode == 0, r.stderr
    changed = _paths_changed(before, _roadmap_planning_bytes(tmp_path))
    committed = set(_commit_files(r.stdout))
    assert committed == changed
    assert t_rel in committed
    assert u_rel in committed
    assert "execution_subtask" not in {
        k for n in load_json_chunk(tmp_path / u_rel) for k in n
    }
