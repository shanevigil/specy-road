"""Tests for ``set-gate-status`` CLI (type gate only)."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from roadmap_chunk_utils import load_json_chunk, write_json_chunk
from tests.helpers import BUNDLED_SCRIPTS, REPO, SCHEMAS, script_subprocess_env


def _sheet(nid: str, _nk: str) -> str:
    return f"# {nid}\n"


def repo_with_gate(dest: Path) -> None:
    """Minimal valid repo: phase + tasks + type gate under phase (M99.4)."""
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
    nk993 = "10000000-0000-4000-8000-000000009905"
    nodes = [
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
        {
            "id": "M99.4",
            "node_key": nk993,
            "parent_id": "M99",
            "type": "gate",
            "title": "Gate",
            "codename": "pytest-gate",
            "planning_dir": f"planning/M99.4_pytest-gate_{nk993}.md",
            "status": "Not Started",
            "touch_zones": [],
            "dependencies": [],
        },
    ]
    pl = dest / "planning"
    pl.mkdir(parents=True)
    (pl / f"M99_unnamed_{nk99}.md").write_text(_sheet("M99", nk99), encoding="utf-8")
    (pl / f"M99.1_one_{nk991}.md").write_text(_sheet("M99.1", nk991), encoding="utf-8")
    (pl / f"M99.2_two_{nk992}.md").write_text(_sheet("M99.2", nk992), encoding="utf-8")
    (pl / f"M99.4_pytest-gate_{nk993}.md").write_text(_sheet("M99.4", nk993), encoding="utf-8")
    write_json_chunk(dest / "roadmap" / "phases" / "T.json", nodes)


def _run_crud(tmp: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(BUNDLED_SCRIPTS / "roadmap_crud.py"), *args],
        cwd=tmp,
        capture_output=True,
        text=True,
        env=script_subprocess_env(),
    )


def test_set_gate_status_cli_updates_gate(tmp_path: Path) -> None:
    repo_with_gate(tmp_path)
    r = _run_crud(
        tmp_path,
        "--repo-root",
        str(tmp_path),
        "set-gate-status",
        "M99.4",
        "--status",
        "Complete",
    )
    assert r.returncode == 0, r.stderr
    nodes = load_json_chunk(tmp_path / "roadmap" / "phases" / "T.json")
    gate = next(n for n in nodes if n["id"] == "M99.4")
    assert gate["status"] == "Complete"


def test_set_gate_status_cli_rejects_task(tmp_path: Path) -> None:
    repo_with_gate(tmp_path)
    r = _run_crud(
        tmp_path,
        "--repo-root",
        str(tmp_path),
        "set-gate-status",
        "M99.1",
        "--status",
        "Complete",
    )
    assert r.returncode == 1
    assert "only applies to type gate" in r.stderr
