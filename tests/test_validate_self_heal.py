"""Tests for the validate self-heal pass (F-006/F-008)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from roadmap_chunk_utils import load_json_chunk, write_json_chunk
from tests.helpers import REPO, SCHEMAS
from validate_self_heal import auto_heal_roadmap


def _bootstrap(dest: Path, nodes: list[dict]) -> None:
    """Build a tiny valid repo with `nodes` in roadmap/phases/T.json."""
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
    write_json_chunk(dest / "roadmap" / "phases" / "T.json", nodes)
    pl = dest / "planning"
    pl.mkdir(parents=True)
    for n in nodes:
        pd = n.get("planning_dir")
        if pd:
            (dest / pd).write_text(f"# {n['id']}\n", encoding="utf-8")


def test_auto_heal_no_change_on_clean_roadmap(tmp_path: Path) -> None:
    """Idempotent: an already-clean tree heals nothing and reports False."""
    nk0 = "10000000-0000-4000-8000-000000000001"
    nk1 = "10000000-0000-4000-8000-000000000002"
    nodes = [
        {
            "id": "M0", "node_key": nk0, "parent_id": None, "type": "phase",
            "title": "P", "status": "Complete",
            "planning_dir": f"planning/M0_unnamed_{nk0}.md",
        },
        {
            "id": "M0.1", "node_key": nk1, "parent_id": "M0", "type": "task",
            "title": "Slug Title", "codename": "slug-title", "status": "Not Started",
            "planning_dir": f"planning/M0.1_slug-title_{nk1}.md",
        },
    ]
    _bootstrap(tmp_path, nodes)
    changed, logs = auto_heal_roadmap(tmp_path)
    assert changed is False
    assert logs == []


def test_auto_heal_derives_missing_codename_and_renames_planning(
    tmp_path: Path,
) -> None:
    nk0 = "10000000-0000-4000-8000-000000000001"
    nk1 = "10000000-0000-4000-8000-000000000002"
    nodes = [
        {
            "id": "M0", "node_key": nk0, "parent_id": None, "type": "phase",
            "title": "P", "status": "Complete",
            "planning_dir": f"planning/M0_unnamed_{nk0}.md",
        },
        {
            "id": "M0.1", "node_key": nk1, "parent_id": "M0", "type": "task",
            "title": "Add Login Form", "status": "Not Started",
            "planning_dir": f"planning/M0.1_unnamed_{nk1}.md",
        },
    ]
    _bootstrap(tmp_path, nodes)
    changed, logs = auto_heal_roadmap(tmp_path)
    assert changed is True
    assert any("auto-derived" in line for line in logs)
    new_nodes = load_json_chunk(tmp_path / "roadmap" / "phases" / "T.json")
    leaf = next(n for n in new_nodes if n["id"] == "M0.1")
    assert leaf["codename"] == "add-login-form"
    assert leaf["planning_dir"] == f"planning/M0.1_add-login-form_{nk1}.md"
    assert (tmp_path / leaf["planning_dir"]).is_file()
    # Old _unnamed_ file should be gone.
    assert not (tmp_path / f"planning/M0.1_unnamed_{nk1}.md").exists()


def test_auto_heal_strips_deprecated_fields(tmp_path: Path) -> None:
    nk0 = "10000000-0000-4000-8000-000000000001"
    nk1 = "10000000-0000-4000-8000-000000000002"
    nodes = [
        {
            "id": "M0", "node_key": nk0, "parent_id": None, "type": "phase",
            "title": "P", "status": "Complete",
            "planning_dir": f"planning/M0_unnamed_{nk0}.md",
        },
        {
            "id": "M0.1", "node_key": nk1, "parent_id": "M0", "type": "task",
            "title": "Old Task", "codename": "old-task", "status": "Not Started",
            "planning_dir": f"planning/M0.1_old-task_{nk1}.md",
            "execution_subtask": "agentic",
            "agentic_checklist": {"artifact_action": "x"},
        },
    ]
    _bootstrap(tmp_path, nodes)
    changed, logs = auto_heal_roadmap(tmp_path)
    assert changed is True
    assert any("execution_subtask" in line for line in logs)
    new_nodes = load_json_chunk(tmp_path / "roadmap" / "phases" / "T.json")
    leaf = next(n for n in new_nodes if n["id"] == "M0.1")
    assert "execution_subtask" not in leaf
    assert "agentic_checklist" not in leaf


def test_auto_heal_codename_collision_uses_uuid_suffix(tmp_path: Path) -> None:
    nk0 = "10000000-0000-4000-8000-000000000001"
    nk1 = "10000000-0000-4000-8000-000000000abc"  # tail = abc -> 'cabc' not last4? last 4 hex of plain key
    nk2 = "10000000-0000-4000-8000-00000000def0"
    nodes = [
        {
            "id": "M0", "node_key": nk0, "parent_id": None, "type": "phase",
            "title": "P", "status": "Complete",
            "planning_dir": f"planning/M0_unnamed_{nk0}.md",
        },
        {
            "id": "M0.1", "node_key": nk1, "parent_id": "M0", "type": "task",
            "title": "Same Title", "codename": "same-title", "status": "Not Started",
            "planning_dir": f"planning/M0.1_same-title_{nk1}.md",
        },
        {
            "id": "M0.2", "node_key": nk2, "parent_id": "M0", "type": "task",
            "title": "Same Title", "status": "Not Started",
            "planning_dir": f"planning/M0.2_unnamed_{nk2}.md",
        },
    ]
    _bootstrap(tmp_path, nodes)
    changed, _logs = auto_heal_roadmap(tmp_path)
    assert changed is True
    new_nodes = load_json_chunk(tmp_path / "roadmap" / "phases" / "T.json")
    leaf2 = next(n for n in new_nodes if n["id"] == "M0.2")
    # Should pick same-title plus a hex suffix from node_key.
    assert leaf2["codename"].startswith("same-title-")
    assert leaf2["codename"] != "same-title"
