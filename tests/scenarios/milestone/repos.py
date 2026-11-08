"""Throwaway repos for the milestone scenarios.

Public on purpose: a scenario test calls these instead of a private helper.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from specy_road.milestone_chunk_io import (
    build_active_milestone_execution,
    write_milestone_execution,
)
from specy_road.registry_yaml import registry_path, write_registry
from tests.milestone_repo_helpers import KEYS, chunk_path, make_milestone_repo
from tests.review_repo_helpers import git

PARENT = "M2"
CODENAME = "milestone-two"
ROLLUP = f"feature/rm-{CODENAME}"
INTEGRATION = "dev"
REMOTE = "origin"
LEAF = "feature/rm-alpha"
# The full-review hold is on by default and keeps a finished milestone's rollup
# off Complete. These scenarios are about the session and reconcile plans, so
# the hold is off and the rollup follows the leaves.
HOLD_OFF = "version: 1\npolicy: {milestone_full_review: false}\n"


def set_parent_codename(root: Path) -> None:
    """Give the parent a codename and the planning filename that must match it."""
    path = chunk_path(root)
    doc = json.loads(path.read_text(encoding="utf-8"))
    parent = next(node for node in doc["nodes"] if node["id"] == PARENT)
    parent["codename"] = CODENAME
    old = root / parent["planning_dir"]
    parent["planning_dir"] = f"planning/{PARENT}_{CODENAME}_{KEYS[PARENT]}.md"
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    (root / parent["planning_dir"]).parent.mkdir(parents=True, exist_ok=True)
    old.rename(root / parent["planning_dir"])


def push_origin(root: Path, branch: str) -> None:
    """A bare ``origin`` the session sync and the rollup git steps can fetch."""
    bare = root.parent / "remote.git"
    if not bare.exists():
        subprocess.check_call(["git", "init", "--bare", "-q", str(bare)])
        git(root, "remote", "add", REMOTE, str(bare))
    git(root, "push", "-q", "-u", REMOTE, branch)


def milestone_repo(tmp_path: Path, *, land: bool) -> Path:
    """The M2 graph on ``dev``, published to ``origin``."""
    root = make_milestone_repo(tmp_path, land=land)
    set_parent_codename(root)
    git(root, "add", "-A")
    git(root, "commit", "-qm", "codename the milestone")
    push_origin(root, INTEGRATION)
    return root


def active_execution() -> dict:
    return build_active_milestone_execution(
        rollup_branch=ROLLUP,
        integration_branch=INTEGRATION,
        remote=REMOTE,
    )


def parent_node(root: Path) -> dict:
    doc = json.loads(chunk_path(root).read_text(encoding="utf-8"))
    return next(node for node in doc["nodes"] if node["id"] == PARENT)


def landed_milestone(tmp_path: Path, *, state: str) -> Path:
    """Both leaves Complete, and ``milestone_execution.state`` set to ``state``."""
    root = make_milestone_repo(tmp_path, orchestration=HOLD_OFF, land=True)
    doc = active_execution()
    doc["state"] = state
    write_milestone_execution(root, PARENT, doc)
    return root


def bookkeeping_repo(tmp_path: Path) -> Path:
    """``dev`` with one registry claim for ``alpha``, and ``origin`` at that tip."""
    bare = tmp_path / "remote.git"
    subprocess.check_call(["git", "init", "--bare", "-q", str(bare)])
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", INTEGRATION)
    git(repo, "config", "user.email", "t@e.com")
    git(repo, "config", "user.name", "T")
    git(repo, "remote", "add", REMOTE, str(bare))
    path = registry_path(repo)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_registry(
        path,
        {
            "version": 1,
            "entries": [
                {
                    "codename": "alpha",
                    "node_id": "M2.1",
                    "branch": LEAF,
                    "touch_zones": ["src/"],
                    "started": "2026-09-01",
                }
            ],
        },
    )
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "register alpha")
    git(repo, "push", "-q", "-u", REMOTE, INTEGRATION)
    return repo
