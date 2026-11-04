"""A one-leaf pickup project with a bare ``origin``, and the CLI run as a user would run it.

Promoted from ``tests/test_baseline_gate_cli.py`` so pickup tests in other
modules share one setup through public names.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

from tests.helpers import SCHEMAS, script_subprocess_env
from tests.review_repo_helpers import git

from specy_road.bundled_scripts.planning_artifacts import expected_planning_rel

SHEET = (
    "## Intent\n\nThe export writes one row per node.\n\n"
    "## Approach\n\nExtend the writer; a golden file test proves it.\n\n"
    "## Tasks / checklist\n\n- [ ] …\n\n## References\n\n- Roadmap chunk for `M1`\n"
)
FEATURE = "feature/rm-leaf-one"


def make_pickup_project(tmp_path: Path, git_workflow_extra: str = "") -> Path:
    """One authored leaf on ``main``, pushed to a bare ``origin``."""
    root = tmp_path / "app"
    (root / "roadmap" / "phases").mkdir(parents=True)
    shutil.copytree(SCHEMAS, root / "schemas")
    node = {
        "id": "M1", "node_key": str(uuid.uuid5(uuid.NAMESPACE_URL, "M1")),
        "codename": "leaf-one", "title": "Leaf one", "type": "task", "parent_id": None,
        "sibling_order": 1, "status": "Not Started", "dependencies": [],
        "touch_zones": ["src"],
    }
    node["planning_dir"] = expected_planning_rel(node)
    (root / node["planning_dir"]).parent.mkdir(parents=True)
    (root / node["planning_dir"]).write_text(SHEET, encoding="utf-8")
    rm = root / "roadmap"
    (rm / "manifest.json").write_text(json.dumps({"version": 1, "includes": ["phases/M1.json"]}))
    (rm / "phases" / "M1.json").write_text(json.dumps({"nodes": [node]}))
    (rm / "registry.yaml").write_text("version: 1\nentries: []\n")
    (rm / "git-workflow.yaml").write_text(
        "version: 1\nintegration_branch: main\nremote: origin\n" + git_workflow_extra
    )
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "t@e.com")
    git(root, "config", "user.name", "T")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "graph")
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
    git(root, "remote", "add", "origin", str(origin))
    git(root, "push", "-q", "-u", "origin", "main")
    git(root, "remote", "set-head", "origin", "main")   # as clone does; fetch does it only from git 2.48
    return root


def run_specy_road(root: Path, *argv: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "specy_road.cli", *argv, "--repo-root", str(root)],
        cwd=root, env=script_subprocess_env(), capture_output=True, text=True,
    )


def run_pickup(root: Path, *argv: str) -> subprocess.CompletedProcess:
    return run_specy_road(root, "do-next-available-task", "--on-complete", "merge", *argv)
