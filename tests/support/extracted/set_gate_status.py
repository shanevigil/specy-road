"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

from pathlib import Path
from tests.helpers import REPO
from tests.helpers import SCHEMAS
import json
import shutil
from specy_road.roadmap_chunk_utils import write_json_chunk

def sheet(nid: str, _nk: str) -> str:
    """Shared test helper."""
    return f"# {nid}\n"

def _gate_nodes() -> list[dict]:
    """The phase, two tasks and the type gate ``repo_with_gate`` writes."""
    nk99 = "10000000-0000-4000-8000-000000009901"
    nk991 = "10000000-0000-4000-8000-000000009902"
    nk992 = "10000000-0000-4000-8000-000000009903"
    nk993 = "10000000-0000-4000-8000-000000009905"
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
    nodes = _gate_nodes()
    keys = {node["id"]: node["node_key"] for node in nodes}
    nk99, nk991, nk992, nk993 = keys["M99"], keys["M99.1"], keys["M99.2"], keys["M99.4"]
    pl = dest / "planning"
    pl.mkdir(parents=True)
    (pl / f"M99_unnamed_{nk99}.md").write_text(sheet("M99", nk99), encoding="utf-8")
    (pl / f"M99.1_one_{nk991}.md").write_text(sheet("M99.1", nk991), encoding="utf-8")
    (pl / f"M99.2_two_{nk992}.md").write_text(sheet("M99.2", nk992), encoding="utf-8")
    (pl / f"M99.4_pytest-gate_{nk993}.md").write_text(sheet("M99.4", nk993), encoding="utf-8")
    write_json_chunk(dest / "roadmap" / "phases" / "T.json", nodes)
