"""Planning files stay aligned with roadmap after outline renumber."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from roadmap_chunk_utils import write_json_chunk
from roadmap_load import load_roadmap
from roadmap_outline_ops import reorder_siblings
from sync_planning_artifacts import sync_planning_artifacts
from tests.helpers import REPO, SCHEMAS
from validate_roadmap import validate_at

_AGENTIC = {
    "artifact_action": "a",
    "contract_citation": "shared/README.md",
    "interface_contract": "i",
    "constraints_note": "c",
    "dependency_note": "d",
}


def _minimal_repo(dest: Path) -> tuple[str, str, str]:
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
    nk0 = "10000000-0000-4000-8000-000000000001"
    nk1 = "10000000-0000-4000-8000-000000000002"
    nk2 = "10000000-0000-4000-8000-000000000003"
    nodes = [
        {
            "id": "M0",
            "node_key": nk0,
            "parent_id": None,
            "type": "phase",
            "title": "P",
            "codename": None,
            "planning_dir": f"planning/M0_unnamed_{nk0}.md",
            "execution_milestone": "Human-led",
            "status": "Complete",
            "touch_zones": [],
            "dependencies": [],
            "parallel_tracks": 1,
            "sibling_order": 0,
        },
        {
            "id": "M0.1",
            "node_key": nk1,
            "parent_id": "M0",
            "type": "task",
            "title": "One",
            "codename": "one",
            "planning_dir": f"planning/M0.1_one_{nk1}.md",
            "execution_milestone": "Agentic-led",
            "execution_subtask": "agentic",
            "agentic_checklist": _AGENTIC,
            "status": "Not Started",
            "touch_zones": [],
            "dependencies": [],
            "parallel_tracks": 1,
            "sibling_order": 0,
        },
        {
            "id": "M0.2",
            "node_key": nk2,
            "parent_id": "M0",
            "type": "task",
            "title": "Two",
            "codename": "two",
            "planning_dir": f"planning/M0.2_two_{nk2}.md",
            "execution_milestone": "Agentic-led",
            "execution_subtask": "agentic",
            "agentic_checklist": _AGENTIC,
            "status": "Not Started",
            "touch_zones": [],
            "dependencies": [nk1],
            "parallel_tracks": 1,
            "sibling_order": 1,
        },
    ]
    pl = dest / "planning"
    pl.mkdir(parents=True)
    (pl / f"M0_unnamed_{nk0}.md").write_text("# M0\n", encoding="utf-8")
    (pl / f"M0.1_one_{nk1}.md").write_text("# M0.1 one\n", encoding="utf-8")
    (pl / f"M0.2_two_{nk2}.md").write_text("# M0.2 two\n", encoding="utf-8")
    write_json_chunk(dest / "roadmap" / "phases" / "T.json", nodes)
    return nk0, nk1, nk2


def test_reorder_siblings_syncs_planning_files(tmp_path: Path) -> None:
    nk0, nk1, nk2 = _minimal_repo(tmp_path)
    reorder_siblings(tmp_path, "M0", ["M0.2", "M0.1"])

    validate_at(tmp_path, no_overlap_warn=True, require_registry=True)

    nodes = load_roadmap(tmp_path)["nodes"]
    by_key = {n["node_key"]: n for n in nodes}
    assert by_key[nk1]["id"] == "M0.2"
    assert by_key[nk2]["id"] == "M0.1"
    assert by_key[nk1]["planning_dir"] == f"planning/M0.2_one_{nk1}.md"
    assert by_key[nk2]["planning_dir"] == f"planning/M0.1_two_{nk2}.md"

    p1 = tmp_path / "planning" / f"M0.2_one_{nk1}.md"
    p2 = tmp_path / "planning" / f"M0.1_two_{nk2}.md"
    assert p1.is_file() and "# M0.1 one" in p1.read_text(encoding="utf-8")
    assert p2.is_file() and "# M0.2 two" in p2.read_text(encoding="utf-8")
    assert not (tmp_path / "planning" / f"M0.1_one_{nk1}.md").exists()
    assert not (tmp_path / "planning" / f"M0.2_two_{nk2}.md").exists()


def test_sync_planning_artifacts_idempotent(tmp_path: Path) -> None:
    _minimal_repo(tmp_path)
    nodes = load_roadmap(tmp_path)["nodes"]
    sync_planning_artifacts(tmp_path, nodes)
    sync_planning_artifacts(tmp_path, nodes)
    validate_at(tmp_path, no_overlap_warn=True, require_registry=True)
