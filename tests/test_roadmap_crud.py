"""Tests for roadmap CRUD and chunk utilities."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from roadmap_chunk_utils import find_chunk_path, load_json_chunk, write_json_chunk
from roadmap_crud_ops import append_node_to_chunk
from tests.helpers import BUNDLED_SCRIPTS, REPO, SCHEMAS, script_subprocess_env


def _sheet_stub(nid: str, _nk: str) -> str:
    return f"# {nid}\n"


def _m99_crud_nodes(nk99: str, nk991: str, nk992: str) -> list[dict]:
    # Post F-003/F-007: execution_subtask/agentic_checklist are gone.
    # Every leaf is agentic by design; no per-node opt-in.
    return [
        {
            "id": "M99",
            "node_key": nk99,
            "parent_id": None,
            "type": "phase",
            "title": "P",
            "codename": None,
            "planning_dir": f"planning/M99_unnamed_{nk99}.md",
            "execution_milestone": "Human-led",
            "status": "Complete",
            "touch_zones": [],
            "dependencies": [],
            "parallel_tracks": 1,
        },
        {
            "id": "M99.1",
            "node_key": nk991,
            "parent_id": "M99",
            "type": "task",
            "title": "One",
            "codename": "one",
            "planning_dir": f"planning/M99.1_one_{nk991}.md",
            "execution_milestone": "Agentic-led",
            "status": "Not Started",
            "touch_zones": [],
            "dependencies": [],
            "parallel_tracks": 1,
        },
        {
            "id": "M99.2",
            "node_key": nk992,
            "parent_id": "M99",
            "type": "task",
            "title": "Two",
            "codename": "two",
            "planning_dir": f"planning/M99.2_two_{nk992}.md",
            "execution_milestone": "Agentic-led",
            "status": "Not Started",
            "touch_zones": [],
            "dependencies": [nk991],
            "parallel_tracks": 1,
        },
    ]


def _fixture_repo(dest: Path) -> None:
    shutil.copytree(SCHEMAS, dest / "schemas")
    shutil.copytree(REPO / "constraints", dest / "constraints")
    (dest / "roadmap" / "phases").mkdir(parents=True)
    (dest / "shared").mkdir(parents=True)
    (dest / "shared" / "README.md").write_text("# Shared\n", encoding="utf-8")
    (dest / "roadmap" / "registry.yaml").write_text(
        "version: 1\nentries: []\n",
        encoding="utf-8",
    )
    (dest / "roadmap" / "manifest.json").write_text(
        json.dumps({"version": 1, "includes": ["phases/T.json"]}) + "\n",
        encoding="utf-8",
    )
    nk99 = "10000000-0000-4000-8000-000000009901"
    nk991 = "10000000-0000-4000-8000-000000009902"
    nk992 = "10000000-0000-4000-8000-000000009903"
    nodes = _m99_crud_nodes(nk99, nk991, nk992)
    pl = dest / "planning"
    pl.mkdir(parents=True)
    (pl / f"M99_unnamed_{nk99}.md").write_text(_sheet_stub("M99", nk99), encoding="utf-8")
    (pl / f"M99.1_one_{nk991}.md").write_text(
        _sheet_stub("M99.1", nk991), encoding="utf-8"
    )
    (pl / f"M99.2_two_{nk992}.md").write_text(_sheet_stub("M99.2", nk992), encoding="utf-8")
    write_json_chunk(dest / "roadmap" / "phases" / "T.json", nodes)


def _run_crud(tmp: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(BUNDLED_SCRIPTS / "roadmap_crud.py"), *args],
        cwd=tmp,
        capture_output=True,
        text=True,
        env=script_subprocess_env(),
    )


def test_find_chunk_path(tmp_path: Path) -> None:
    _fixture_repo(tmp_path)
    assert find_chunk_path(tmp_path, "M99.1") == tmp_path / "roadmap" / "phases" / "T.json"


def test_append_node_validate(tmp_path: Path) -> None:
    _fixture_repo(tmp_path)
    nk = "10000000-0000-4000-8000-000000009904"
    node = {
        "id": "M99.3",
        "node_key": nk,
        "parent_id": "M99",
        "type": "task",
        "title": "Three",
        "codename": "three",
        "planning_dir": f"planning/M99.3_three_{nk}.md",
        "execution_milestone": "Agentic-led",
        "status": "Not Started",
        "touch_zones": [],
        "dependencies": [],
        "parallel_tracks": 1,
    }
    p = tmp_path / "planning" / f"M99.3_three_{nk}.md"
    p.write_text("# M99.3\n", encoding="utf-8")
    append_node_to_chunk(tmp_path, "phases/T.json", node)
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


def test_archive_node_unknown_id_message(tmp_path: Path) -> None:
    _fixture_repo(tmp_path)
    r = _run_crud(
        tmp_path,
        "--repo-root",
        str(tmp_path),
        "archive-node",
        "M404.1",
        "--hard-remove",
    )
    assert r.returncode == 1
    assert "no roadmap node" in r.stderr
    assert "M404.1" in r.stderr


def test_hard_remove_blocked_by_dependency(tmp_path: Path) -> None:
    _fixture_repo(tmp_path)
    r = _run_crud(
        tmp_path,
        "--repo-root",
        str(tmp_path),
        "archive-node",
        "M99.1",
        "--hard-remove",
    )
    assert r.returncode == 1
    assert "depends" in r.stderr


def test_hard_remove_deletes_planning_file(tmp_path: Path) -> None:
    _fixture_repo(tmp_path)
    nk992 = "10000000-0000-4000-8000-000000009903"
    planning = tmp_path / "planning" / f"M99.2_two_{nk992}.md"
    assert planning.is_file()
    r = _run_crud(
        tmp_path,
        "--repo-root",
        str(tmp_path),
        "archive-node",
        "M99.2",
        "--hard-remove",
    )
    assert r.returncode == 0, r.stderr
    assert not planning.exists()
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


def test_edit_node_cli(tmp_path: Path) -> None:
    _fixture_repo(tmp_path)
    r = _run_crud(
        tmp_path,
        "--repo-root",
        str(tmp_path),
        "edit-node",
        "M99.1",
        "--set",
        "status=Complete",
    )
    assert r.returncode == 0, r.stderr


def test_edit_node_cli_rejects_invalid_status(tmp_path: Path) -> None:
    _fixture_repo(tmp_path)
    r = _run_crud(
        tmp_path,
        "--repo-root",
        str(tmp_path),
        "edit-node",
        "M99.1",
        "--set",
        "status=Bad",
    )
    assert r.returncode == 1
    assert "status must be one of" in r.stderr


def test_list_nodes_cli(tmp_path: Path) -> None:
    _fixture_repo(tmp_path)
    r = _run_crud(tmp_path, "--repo-root", str(tmp_path), "list-nodes")
    assert r.returncode == 0
    assert "M99.1" in r.stdout


def test_show_node_cli(tmp_path: Path) -> None:
    _fixture_repo(tmp_path)
    r = _run_crud(tmp_path, "--repo-root", str(tmp_path), "show-node", "M99.1")
    assert r.returncode == 0
    assert "# chunk: roadmap/phases/T.json" in r.stdout
    assert '"id": "M99.1"' in r.stdout


def test_archive_node_without_hard_remove_is_rejected(tmp_path: Path) -> None:
    _fixture_repo(tmp_path)
    r = _run_crud(tmp_path, "--repo-root", str(tmp_path), "archive-node", "M99.1")
    assert r.returncode == 1, r.stderr
    assert "hard-remove" in (r.stderr + r.stdout).lower()
    nodes = load_json_chunk(tmp_path / "roadmap" / "phases" / "T.json")
    node = next(n for n in nodes if n["id"] == "M99.1")
    assert node["status"] != "Cancelled"


def test_hard_remove_leaf_node_succeeds(tmp_path: Path) -> None:
    _fixture_repo(tmp_path)
    r = _run_crud(
        tmp_path,
        "--repo-root",
        str(tmp_path),
        "archive-node",
        "M99.2",
        "--hard-remove",
    )
    assert r.returncode == 0, r.stderr
    nodes = load_json_chunk(tmp_path / "roadmap" / "phases" / "T.json")
    ids = {n["id"] for n in nodes}
    assert "M99.2" not in ids
    assert "M99.1" in ids


def test_edit_node_cli_rejects_non_key_value_set(tmp_path: Path) -> None:
    _fixture_repo(tmp_path)
    r = _run_crud(
        tmp_path,
        "--repo-root",
        str(tmp_path),
        "edit-node",
        "M99.1",
        "--set",
        "status",
    )
    assert r.returncode == 1
    assert "expected key=value" in r.stderr


def test_add_node_cli_rejects_unknown_parent(tmp_path: Path) -> None:
    _fixture_repo(tmp_path)
    r = _run_crud(
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
        "M404",
        "--codename",
        "three",
    )
    assert r.returncode == 1
    assert "parent_id 'M404' not found in roadmap" in r.stderr


def test_add_node_rejects_removed_execution_subtask_flag(tmp_path: Path) -> None:
    """Per F-003/F-007 the --execution-subtask flag was removed."""
    _fixture_repo(tmp_path)
    r = _run_crud(
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
        "--execution-subtask",
        "agentic",
    )
    assert r.returncode != 0
    assert "unrecognized arguments" in r.stderr or "--execution-subtask" in r.stderr


def test_add_node_chunk_arg_optional(tmp_path: Path) -> None:
    """F-AUTO: ``--chunk`` is no longer required; the router auto-routes."""
    _fixture_repo(tmp_path)
    r = _run_crud(
        tmp_path,
        "--repo-root",
        str(tmp_path),
        "add-node",
        "--id",
        "M99.3",
        "--type",
        "task",
        "--title",
        "No chunk arg",
        "--parent-id",
        "M99",
    )
    assert r.returncode == 0, r.stderr
    nodes = load_json_chunk(tmp_path / "roadmap" / "phases" / "T.json")
    assert any(n["id"] == "M99.3" for n in nodes)


def test_add_node_auto_creates_chunk_when_target_full(tmp_path: Path) -> None:
    """F-AUTO: when the hint chunk is full the router auto-creates a new chunk."""
    _fixture_repo(tmp_path)
    # Tighten the cap so the existing 3-node chunk fits but adding any
    # non-trivial node would push it over the limit.
    cur = load_json_chunk(tmp_path / "roadmap" / "phases" / "T.json")
    from roadmap_chunk_router_pick import simulate_chunk_lines

    current_lines = simulate_chunk_lines(cur)
    cap = current_lines + 5  # tight: another node won't fit
    (tmp_path / "constraints" / "file-limits.yaml").write_text(
        f"roadmap_json_chunk_max_lines: {cap}\n", encoding="utf-8"
    )
    r = _run_crud(
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
    # The new node landed in a new chunk; the original chunk is unchanged.
    src = load_json_chunk(tmp_path / "roadmap" / "phases" / "T.json")
    assert all(n["id"] != "M99.5" for n in src)
    new_chunks = sorted(
        p for p in (tmp_path / "roadmap" / "phases").iterdir()
        if p.suffix == ".json" and p.name != "T.json"
    )
    assert len(new_chunks) == 1
    new_nodes = load_json_chunk(new_chunks[0])
    assert any(n["id"] == "M99.5" for n in new_nodes)


def test_add_node_no_codename_auto_derives(tmp_path: Path) -> None:
    """F-006: when --codename is omitted on a task, it's auto-derived from --title."""
    _fixture_repo(tmp_path)
    r = _run_crud(
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
        "Three Slug",
        "--parent-id",
        "M99",
    )
    assert r.returncode == 0, r.stderr
    nodes = load_json_chunk(tmp_path / "roadmap" / "phases" / "T.json")
    node = next(n for n in nodes if n["id"] == "M99.3")
    assert node["codename"] == "three-slug"
