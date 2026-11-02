"""Throwaway git repos for ``specy-road integrity`` tests.

``dev`` is the integration branch and ``feature`` the leaf branch; a test commits
the baseline on ``dev``, merges it into ``feature`` and commits the REF change there.
``make_repo(..., roadmap=True)`` adds a one-leaf roadmap (``T1`` on ``feature``) for
CLI tests, under ``project`` when the project root is nested.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import yaml

from tests.helpers import DOGFOOD


def git(repo: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)
    return r.stdout.strip()


def commit(repo: Path, rel: str, text: str, msg: str) -> str:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    git(repo, "add", rel)
    git(repo, "commit", "-qm", msg)
    return git(repo, "rev-parse", "HEAD")


def merge_base(repo: Path) -> str:
    return git(repo, "merge-base", "dev", "HEAD")


def on_dev(repo: Path) -> None:
    git(repo, "checkout", "-q", "dev")


def on_feature(repo: Path) -> None:
    git(repo, "checkout", "-q", "feature")


def write_roadmap(repo: Path, project: str = "") -> None:
    on_dev(repo)
    proj = repo / project
    shutil.copytree(DOGFOOD / "schemas", proj / "schemas")
    (proj / "roadmap" / "phases").mkdir(parents=True, exist_ok=True)
    (proj / "roadmap" / "manifest.json").write_text('{"version": 1, "includes": ["phases/T.json"]}', encoding="utf-8")
    node = {
        "id": "T1",
        "node_key": "11111111-1111-5111-8111-111111111111",
        "codename": "t",
        "title": "T",
        "type": "task",
        "parent_id": None,
        "sibling_order": 1,
        "status": "In Progress",
        "dependencies": [],
        "touch_zones": ["src"],
    }
    (proj / "roadmap" / "phases" / "T.json").write_text(json.dumps({"nodes": [node]}), encoding="utf-8")
    (proj / "roadmap" / "git-workflow.yaml").write_text(
        "version: 1\nintegration_branch: dev\nremote: origin\n", encoding="utf-8"
    )
    entry = {"codename": "t", "node_id": "T1", "branch": "feature"}
    (proj / "roadmap" / "registry.yaml").write_text(
        yaml.safe_dump({"version": 1, "entries": [entry]}), encoding="utf-8"
    )
    git(repo, "add", str(proj / "roadmap"), str(proj / "schemas"))
    git(repo, "commit", "-qm", "roadmap")


def make_repo(tmp_path: Path, *, roadmap: bool = False, project: str = "") -> Path:
    root = tmp_path / "r"
    root.mkdir()
    git(root, "init", "-q", "-b", "dev")
    git(root, "config", "user.email", "t@e.com")
    git(root, "config", "user.name", "T")
    commit(root, "README.md", "# r\n", "init")
    if roadmap:
        write_roadmap(root, project)
    git(root, "checkout", "-q", "-b", "feature")
    return root


def merge_dev(repo: Path) -> None:
    on_feature(repo)
    git(repo, "merge", "dev", "--no-edit")
