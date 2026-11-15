"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

from tests.helpers import DOGFOOD
from pathlib import Path
import json
import os
import pytest
import shutil
import subprocess

_ENV = {
    "GIT_AUTHOR_NAME": "pat",
    "GIT_AUTHOR_EMAIL": "pat@example.com",
    "GIT_COMMITTER_NAME": "pat",
    "GIT_COMMITTER_EMAIL": "pat@example.com",
}

M01_KEY = "44ef4a9d-923f-545c-8187-eaabc7ca86ba"

M2_KEY = "4c1d98f2-2bdc-4a7d-81b9-c6f7e96e95f0"

M03_KEY = "cd44fef1-715a-5b8d-b03f-1752a61a47cc"

def git(repo: Path, *args: str) -> str:
    env = os.environ.copy()
    env.update(_ENV)
    r = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True, env=env
    )
    return r.stdout.strip()

def commit(repo: Path, message: str) -> str:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "--allow-empty", "-m", message)
    return git(repo, "rev-parse", "HEAD")

@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    """The dogfood fixture as a real git repo with one baseline commit."""
    dest = tmp_path / "repo"
    shutil.copytree(DOGFOOD, dest)
    git(dest, "init", "-q", "-b", "main")
    commit(dest, "baseline roadmap")
    return dest

def write_chunk(path: Path, doc: dict) -> None:
    path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")

def edit_node(repo: Path, node_id: str, **fields: object) -> None:
    """Update a node wherever it lives — the fixture spreads them over chunks."""
    for path in sorted((repo / "roadmap" / "phases").glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        if any(n["id"] == node_id for n in doc["nodes"]):
            for node in doc["nodes"]:
                if node["id"] == node_id:
                    node.update(fields)
            write_chunk(path, doc)
            return
    raise AssertionError(f"no node {node_id} in the fixture")
