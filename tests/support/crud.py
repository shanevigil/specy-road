"""The CRUD fixture: phase ``M99`` with two leaves, edited through the roadmap_crud script."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from tests.helpers import REPO, SCHEMAS, script_subprocess_env
from tests.support.cli import run_script
from tests.support.roadmap import roadmap_repo


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


def crud_fixture_repo(dest: Path) -> None:
    """Phase ``M99`` with leaves ``M99.1`` and ``M99.2`` (needs ``M99.1``) in ``phases/T.json``."""
    shutil.copytree(SCHEMAS, dest / "schemas")
    shutil.copytree(REPO / "constraints", dest / "constraints")
    (dest / "shared").mkdir(parents=True)
    (dest / "shared" / "README.md").write_text("# Shared\n", encoding="utf-8")
    nodes = _m99_crud_nodes(
        "10000000-0000-4000-8000-000000009901",
        "10000000-0000-4000-8000-000000009902",
        "10000000-0000-4000-8000-000000009903",
    )
    roadmap_repo(dest, nodes, chunk="phases/T.json")


def run_crud(tmp: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run ``roadmap_crud.py <args>`` from ``tmp`` in this process; never raises on its exit."""
    return run_script("roadmap_crud.py", list(args), cwd=tmp, env=script_subprocess_env())


def write_registry_claim(
    tmp_path: Path, node_id: str, codename: str, branch: str, owner: str
) -> None:
    """Replace the registry with one claim of ``node_id`` on ``branch``."""
    (tmp_path / "roadmap" / "registry.yaml").write_text(
        f"""version: 1
entries:
  - codename: {codename}
    node_id: {node_id}
    branch: {branch}
    owner: {owner}
""",
        encoding="utf-8",
    )


def edit_m99_1(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """``edit-node M99.1 <args>`` on the fixture at ``tmp_path``."""
    return run_crud(tmp_path, "--repo-root", str(tmp_path), "edit-node", "M99.1", *args)
