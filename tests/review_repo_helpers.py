"""A throwaway git repo with one claimed leaf, for review hand-off tests.

``dev`` holds the graph and the registry claim; ``feature/rm-thing`` adds one
file inside the touch zone (``src/a.py``) and one outside it (``docs/x.md``).
The repo is left on the feature branch.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import yaml

NODE = {
    "id": "M1.1",
    "node_key": "11111111-1111-5111-8111-111111111111",
    "codename": "thing",
    "title": "Thing",
    "type": "task",
    "parent_id": None,
    "sibling_order": 1,
    "status": "In Progress",
    "dependencies": [],
    "touch_zones": ["src"],
    "goal": "Do the thing.",
    "acceptance": ["a.py exists", "nothing else breaks"],
}


def git(repo: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)
    return r.stdout.strip()


def commit_file(repo: Path, rel: str, text: str, msg: str) -> str:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    git(repo, "add", rel)
    git(repo, "commit", "-qm", msg)
    return git(repo, "rev-parse", "HEAD")


def make_review_repo(tmp_path: Path, *, orchestration: str | None = None) -> Path:
    root = tmp_path / "r"
    (root / "roadmap" / "phases").mkdir(parents=True)
    git(root, "init", "-q", "-b", "dev")
    git(root, "config", "user.email", "t@e.com")
    git(root, "config", "user.name", "T")
    rm = root / "roadmap"
    (rm / "manifest.json").write_text(
        json.dumps({"version": 1, "includes": ["phases/M1.json"]}), encoding="utf-8"
    )
    (rm / "phases" / "M1.json").write_text(json.dumps({"nodes": [NODE]}), encoding="utf-8")
    (rm / "git-workflow.yaml").write_text(
        "version: 1\nintegration_branch: dev\nremote: origin\n"
        "require_implementation_review_before_finish: true\n",
        encoding="utf-8",
    )
    entry = {"codename": "thing", "node_id": "M1.1", "branch": "feature/rm-thing",
             "touch_zones": ["src"], "implementation_review": "pending"}
    (rm / "registry.yaml").write_text(
        yaml.safe_dump({"version": 1, "entries": [entry]}), encoding="utf-8"
    )
    if orchestration is not None:
        (rm / "orchestration.yaml").write_text(orchestration, encoding="utf-8")
    (root / ".gitignore").write_text("work/reviews/\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "graph")
    git(root, "checkout", "-q", "-b", "feature/rm-thing")
    commit_file(root, "src/a.py", "print('a')\n", "impl")
    commit_file(root, "docs/x.md", "# x\n", "stray")
    return root


def review_text(commit: str, *, model: str = "human", verdict: str = "approve",
                fresh: bool = True, a1: str = "pass") -> str:
    data = {
        "node_id": "M1.1", "model": model, "date": "2026-10-26", "verdict": verdict,
        "commit": commit, "acceptance": {"A1": a1, "A2": "pass"},
        "findings": {"correctness": [], "regression": [], "boundary": [], "test_integrity": []},
        "commands_rerun": [], "required_changes": [] if verdict == "approve" else ["fix"],
        "fresh_session": fresh, "authored_fix": False, "is_coordinator": False,
    }
    return "---\n" + yaml.safe_dump(data, sort_keys=False) + "---\nnotes\n"
