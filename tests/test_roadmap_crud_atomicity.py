"""Rejected roadmap mutations must leave the working tree untouched.

Regression cover for the v0.1.4-rc2 report: ``edit-node`` wrote its chunk (and
renamed the planning sheet) before validating, and ``add-node`` scaffolded the
planning sheet outside its transaction. Either way a refused command left the
repo in a state where ``validate`` failed, which blocked every later command.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from specy_road.bundled_scripts.roadmap_chunk_utils import load_json_chunk, write_json_chunk
from specy_road.bundled_scripts.roadmap_crud_ops import (
    append_node_to_chunk,
    delete_roadmap_node_hard,
    edit_node_set_pairs,
)
from specy_road.bundled_scripts.roadmap_codename_cap import cap_codename_slug
from specy_road.bundled_scripts.roadmap_edit_fields import CODENAME_MAX_CHARS, title_to_codename
from tests.helpers import BUNDLED_SCRIPTS, REPO, SCHEMAS, script_subprocess_env

NK_PHASE = "20000000-0000-4000-8000-000000000001"
NK_TASK = "20000000-0000-4000-8000-000000000002"


def _nodes() -> list[dict]:
    return [
        {
            "id": "M50",
            "node_key": NK_PHASE,
            "parent_id": None,
            "type": "phase",
            "title": "Atomicity phase",
            "planning_dir": f"planning/M50_unnamed_{NK_PHASE}.md",
            "status": "Not Started",
            "touch_zones": [],
            "dependencies": [],
        },
        {
            "id": "M50.1",
            "node_key": NK_TASK,
            "parent_id": "M50",
            "type": "task",
            "title": "Atomicity leaf",
            "codename": "atomicity-leaf",
            "planning_dir": f"planning/M50.1_atomicity-leaf_{NK_TASK}.md",
            "status": "Not Started",
            "touch_zones": [],
            "dependencies": [],
        },
    ]


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    shutil.copytree(SCHEMAS, tmp_path / "schemas")
    shutil.copytree(REPO / "constraints", tmp_path / "constraints")
    (tmp_path / "roadmap" / "phases").mkdir(parents=True)
    (tmp_path / "shared").mkdir()
    (tmp_path / "shared" / "README.md").write_text("# Shared\n", encoding="utf-8")
    (tmp_path / "roadmap" / "registry.yaml").write_text(
        "version: 1\nentries: []\n", encoding="utf-8"
    )
    (tmp_path / "roadmap" / "manifest.json").write_text(
        json.dumps({"version": 1, "includes": ["phases/T.json"]}) + "\n",
        encoding="utf-8",
    )
    planning = tmp_path / "planning"
    planning.mkdir()
    for node in _nodes():
        rel = node["planning_dir"].split("/", 1)[1]
        (planning / rel).write_text(f"# {node['id']}\n", encoding="utf-8")
    write_json_chunk(tmp_path / "roadmap" / "phases" / "T.json", _nodes())
    return tmp_path


def _snapshot(root: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            out[str(path.relative_to(root))] = path.read_text(encoding="utf-8")
    return out


def _run(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(BUNDLED_SCRIPTS / "roadmap_crud.py"), *args],
        cwd=root,
        capture_output=True,
        text=True,
        env=script_subprocess_env(),
    )


def test_rejected_edit_changes_nothing_on_disk(repo: Path) -> None:
    before = _snapshot(repo)
    with pytest.raises(ValueError, match="duplicate title"):
        edit_node_set_pairs(repo, "M50.1", [("title", "Atomicity phase")])
    assert _snapshot(repo) == before


def test_rejected_edit_does_not_rename_the_planning_sheet(repo: Path) -> None:
    """A title change resyncs planning_dir; a rejected change must not move the file."""
    sheet = repo / "planning" / f"M50.1_atomicity-leaf_{NK_TASK}.md"
    before = _snapshot(repo)
    with pytest.raises(ValueError, match="duplicate title"):
        edit_node_set_pairs(repo, "M50.1", [("title", "Atomicity phase")])
    assert sheet.is_file()
    assert _snapshot(repo) == before


def test_accepted_edit_renames_the_planning_sheet(repo: Path) -> None:
    edit_node_set_pairs(repo, "M50.1", [("title", "Renamed leaf")])
    assert not (repo / "planning" / f"M50.1_atomicity-leaf_{NK_TASK}.md").exists()
    assert (repo / "planning" / f"M50.1_renamed-leaf_{NK_TASK}.md").is_file()
    nodes = load_json_chunk(repo / "roadmap" / "phases" / "T.json")
    edited = next(n for n in nodes if n["id"] == "M50.1")
    assert edited["planning_dir"] == f"planning/M50.1_renamed-leaf_{NK_TASK}.md"


def test_rejected_add_node_leaves_no_orphan_planning_sheet(repo: Path) -> None:
    """The sheet is staged with the chunk, so a schema rejection rolls it back too."""
    schema_path = repo / "schemas" / "roadmap.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    schema["$defs"]["node"]["properties"]["type"]["enum"] = [
        "vision",
        "phase",
        "milestone",
        "task",
    ]
    schema_path.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
    before = _snapshot(repo)

    r = _run(
        repo,
        "--repo-root",
        str(repo),
        "add-node",
        "--id",
        "M50.2",
        "--parent-id",
        "M50",
        "--type",
        "gate",
        "--title",
        "Refused gate",
    )
    assert r.returncode == 1, r.stdout + r.stderr
    assert "is not one of" in r.stderr
    assert _snapshot(repo) == before
    assert not list((repo / "planning").glob("M50.2_*"))


def test_rejected_add_of_a_codenameless_task_leaves_nothing_behind(repo: Path) -> None:
    """The self-heal pass must not rename a staged sheet from inside the transaction.

    A task with no codename used to be healed during the mutation's own
    validation: the heal derived a codename, renamed the just-staged planning
    sheet to match, and the rollback then unlinked the pre-rename path — leaving
    the renamed sheet as an orphan the PM GUI hit on every refused add.
    """
    schema_path = repo / "schemas" / "roadmap.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    schema["$defs"]["node"]["properties"]["title"]["minLength"] = 400
    schema_path.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
    sheets_before = sorted(p.name for p in (repo / "planning").iterdir())

    node = {
        "id": "M50.2",
        "node_key": "20000000-0000-4000-8000-000000000003",
        "parent_id": "M50",
        "type": "task",
        "title": "Refused leaf",
        "status": "Not Started",
        "touch_zones": [],
        "dependencies": [],
    }
    with pytest.raises(ValueError, match="too short"):
        append_node_to_chunk(repo, None, node)

    assert sorted(p.name for p in (repo / "planning").iterdir()) == sheets_before


def test_add_derives_a_codename_before_writing(repo: Path) -> None:
    node = {
        "id": "M50.2",
        "node_key": "20000000-0000-4000-8000-000000000004",
        "parent_id": "M50",
        "type": "task",
        "title": "Accepted leaf",
        "status": "Not Started",
        "touch_zones": [],
        "dependencies": [],
    }
    append_node_to_chunk(repo, None, node)
    assert node["codename"] == "accepted-leaf"
    assert (
        repo / "planning" / f"M50.2_accepted-leaf_{node['node_key']}.md"
    ).is_file()


def test_rejected_hard_remove_keeps_the_planning_sheet(repo: Path) -> None:
    """M50.1's parent still has a child, so removing M50 must be refused cleanly."""
    before = _snapshot(repo)
    with pytest.raises(ValueError, match="child node"):
        delete_roadmap_node_hard(repo, "M50")
    assert _snapshot(repo) == before


def test_accepted_hard_remove_takes_the_planning_sheet(repo: Path) -> None:
    delete_roadmap_node_hard(repo, "M50.1")
    assert not (repo / "planning" / f"M50.1_atomicity-leaf_{NK_TASK}.md").exists()
    nodes = load_json_chunk(repo / "roadmap" / "phases" / "T.json")
    assert [n["id"] for n in nodes] == ["M50"]


def test_validation_warnings_are_not_relabelled_as_errors(repo: Path) -> None:
    """A refused mutation must not print unrelated warnings under an `error:` prefix."""
    schema_path = repo / "schemas" / "roadmap.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    schema["$defs"]["node"]["properties"]["title"]["description"] = "Reworded."
    del schema["$defs"]["node"]["properties"]["decision"]
    schema_path.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")

    r = _run(
        repo,
        "--repo-root",
        str(repo),
        "edit-node",
        "M50.1",
        "--set",
        "title=Atomicity phase",
    )
    assert r.returncode == 1, r.stdout + r.stderr
    assert "schemas: warning" in r.stderr
    assert "error: schemas: warning" not in r.stderr
    assert "error: roadmap: duplicate title" in r.stderr


def test_mutation_output_does_not_leak_validation_success_line(repo: Path) -> None:
    r = _run(
        repo,
        "--repo-root",
        str(repo),
        "edit-node",
        "M50.1",
        "--set",
        "status=Complete",
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "OK: roadmap and registry validate." not in r.stdout
    assert "[ok] updated M50.1" in r.stdout


def test_add_node_long_title_caps_derived_codename(repo: Path) -> None:
    title = " ".join(f"segment{i}" for i in range(40))  # well over 300 characters
    assert len(title) >= 300
    r = _run(
        repo,
        "--repo-root",
        str(repo),
        "add-node",
        "--id",
        "M50.2",
        "--parent-id",
        "M50",
        "--type",
        "task",
        "--title",
        title,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    nodes = load_json_chunk(repo / "roadmap" / "phases" / "T.json")
    node = next(n for n in nodes if n["id"] == "M50.2")
    uncapped = title_to_codename(title)
    codename = node["codename"]
    assert codename is not None
    assert len(codename) <= CODENAME_MAX_CHARS
    assert codename == cap_codename_slug(uncapped)
    assert uncapped.startswith(codename) or codename in uncapped
    sheet_name = node["planning_dir"].split("/", 1)[1]
    assert len(sheet_name.encode("utf-8")) <= 255
    assert (repo / "planning" / sheet_name).is_file()


def test_add_node_refuses_explicit_codename_over_64_chars(repo: Path) -> None:
    too_long = "a" * 65
    before = _snapshot(repo)
    r = _run(
        repo,
        "--repo-root",
        str(repo),
        "add-node",
        "--id",
        "M50.2",
        "--parent-id",
        "M50",
        "--type",
        "task",
        "--title",
        "Short title",
        "--codename",
        too_long,
    )
    assert r.returncode == 1, r.stdout + r.stderr
    assert (
        r.stderr.strip()
        == "error: codename is 65 characters; the limit is 64 "
        "(it names feature/rm-<codename> and the planning file)"
    )
    assert _snapshot(repo) == before


def test_edit_node_refuses_codename_over_64_chars(repo: Path) -> None:
    too_long = "b" * 65
    before = _snapshot(repo)
    r = _run(
        repo,
        "--repo-root",
        str(repo),
        "edit-node",
        "M50.1",
        "--set",
        f"codename={too_long}",
    )
    assert r.returncode == 1, r.stdout + r.stderr
    assert "error: codename is 65 characters; the limit is 64" in r.stderr
    assert _snapshot(repo) == before


def _roadmap_bytes(root: Path) -> dict[str, bytes]:
    folder = root / "roadmap"
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(folder.rglob("*")) if p.is_file()}


def test_plan_write_failure_restores_the_chunk_and_removes_temp_files(repo: Path) -> None:
    """A write that fails after the chunk landed rolls the chunk back (M15.39 A3a)."""
    from specy_road.bundled_scripts.roadmap_chunk_atomic import AtomicWritePlan

    chunk = repo / "roadmap" / "phases" / "T.json"
    original = chunk.read_bytes()
    plan = AtomicWritePlan(root=repo)
    plan.stage_chunk(chunk, _nodes()[:1])
    plan.stage_text(repo / "planning" / ("x" * 300 + ".md"), "# too long\n")
    with pytest.raises(OSError):
        plan.commit(lambda: None)
    assert chunk.read_bytes() == original
    assert not [p for p in repo.rglob("*") if ".tmp-" in p.name]


def test_add_node_write_failure_restores_the_roadmap(repo: Path) -> None:
    """planning/ is a regular file, so the sheet write fails after the chunk write (A3b)."""
    shutil.rmtree(repo / "planning")
    (repo / "planning").write_text("not a directory\n", encoding="utf-8")
    before = _roadmap_bytes(repo)
    r = _run(
        repo, "--repo-root", str(repo), "add-node", "--id", "M50.2",
        "--parent-id", "M50", "--type", "task", "--title", "Doomed leaf",
    )
    assert r.returncode == 1, r.stdout + r.stderr
    assert len([ln for ln in r.stderr.splitlines() if ln.startswith("error: ")]) == 1, r.stderr
    assert "Traceback" not in r.stderr
    assert _roadmap_bytes(repo) == before


@pytest.mark.skipif(
    sys.platform == "win32" or getattr(os, "geteuid", lambda: 1)() == 0,
    reason="needs POSIX permissions and a non-root user",
)
def test_edit_node_sheet_rename_failure_restores_the_roadmap(repo: Path) -> None:
    """planning/ is read-only, so the sheet rename fails after the chunk write (A3c)."""
    planning = repo / "planning"
    before = _roadmap_bytes(repo)
    planning.chmod(0o555)
    try:
        r = _run(
            repo, "--repo-root", str(repo), "edit-node", "M50.1",
            "--set", "title=Renamed leaf",
        )
    finally:
        planning.chmod(0o755)
    assert r.returncode == 1, r.stdout + r.stderr
    assert len([ln for ln in r.stderr.splitlines() if ln.startswith("error: ")]) == 1, r.stderr
    assert "Traceback" not in r.stderr
    assert _roadmap_bytes(repo) == before
    assert (planning / f"M50.1_atomicity-leaf_{NK_TASK}.md").is_file()
