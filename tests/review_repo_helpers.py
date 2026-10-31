"""A throwaway git repo with one claimed leaf, for review hand-off tests.

``dev`` holds the graph and the registry claim; ``feature/rm-thing`` adds one
file inside the touch zone (``src/a.py``) and one outside it (``docs/x.md``).
The repo is left on the feature branch.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import yaml

from tests.helpers import DOGFOOD

#: Git-root file changed on the nested-outside layout shape (outside ``sr/``).
OUTSIDE_ROOT_FILE = "README.md"

#: ``make_layout_finish_repo`` shapes exercised in ``test_project_layouts_outside.py``.
LAYOUT_FINISH_SHAPES = ("embedded", "nested", "nested_outside")

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
    "planning_dir": "planning/M1.1_thing_11111111-1111-5111-8111-111111111111.md",
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


def advance_dev(repo: Path, rel: str, text: str) -> None:
    """Commit ``rel`` on ``dev`` after the feature branched; the repo stays on the feature branch."""
    git(repo, "checkout", "-q", "dev")
    commit_file(repo, rel, text, "dev moves on")
    git(repo, "checkout", "-q", "feature/rm-thing")


#: Trial-merge cases: what ``dev`` commits after the branch, and whether the
#: feature branch edits the same file first. ``src/a.py`` is the branch's own file.
TRIAL_MERGES = {
    "clean": ("other.txt", False),
    "bookkeeping": (NODE["planning_dir"], True),
    "code": ("src/a.py", False),
}


def diverge(repo: Path, case: str) -> str:
    """Set up one :data:`TRIAL_MERGES` case; return the path ``dev`` changed."""
    rel, both = TRIAL_MERGES[case]
    if both:
        commit_file(repo, rel, "feature side\n", "feature edits it too")
    advance_dev(repo, rel, "dev side\n")
    return rel


def layout_prefix(shape: str) -> str:
    return "" if shape == "embedded" else "sr/"


def touch_zones_for_layout(shape: str) -> list[str]:
    if shape == "nested_outside":
        return [OUTSIDE_ROOT_FILE]
    return ["src"]


def git_root_relative(git_top: Path, project: Path, project_rel: str) -> str:
    from specy_road.runtime_paths import prefix_within

    prefix = prefix_within(git_top, project)
    return f"{prefix}{project_rel}" if prefix else project_rel


def make_layout_finish_repo(tmp_path: Path, shape: str) -> tuple[Path, Path]:
    """Minimal claimed leaf in ``shape``; returns ``(git_root, project_root)`` on ``feature/rm-thing``."""
    git_top = tmp_path / "checkout"
    git_top.mkdir(parents=True, exist_ok=True)
    prefix = layout_prefix(shape)
    project = git_top / prefix.rstrip("/") if prefix else git_top
    if prefix:
        project.mkdir(parents=True)
    shutil.copytree(DOGFOOD / "schemas", project / "schemas")
    git(git_top, "init", "-q", "-b", "dev")
    git(git_top, "config", "user.email", "t@e.com")
    git(git_top, "config", "user.name", "T")
    if prefix:
        manifest = git_top / ".specyrd" / "manifest.json"
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(
            json.dumps({"project_root": prefix.rstrip("/")}) + "\n",
            encoding="utf-8",
        )
    rm = project / "roadmap"
    rm.mkdir(parents=True)
    (rm / "phases").mkdir(parents=True)
    zones = touch_zones_for_layout(shape)
    node = {**NODE, "touch_zones": zones}
    (rm / "manifest.json").write_text(
        json.dumps({"version": 1, "includes": ["phases/M1.json"]}), encoding="utf-8"
    )
    (rm / "phases" / "M1.json").write_text(json.dumps({"nodes": [node]}), encoding="utf-8")
    sheet = project / NODE["planning_dir"]
    sheet.parent.mkdir(parents=True, exist_ok=True)
    sheet.write_text("# M1.1 Thing\n\n## Intent\n\nDo the thing.\n\n## References\n", encoding="utf-8")
    (rm / "git-workflow.yaml").write_text(
        "version: 1\nintegration_branch: dev\nremote: origin\n"
        "require_implementation_review_before_finish: true\n",
        encoding="utf-8",
    )
    entry = {
        "codename": "thing",
        "node_id": "M1.1",
        "branch": "feature/rm-thing",
        "touch_zones": zones,
        "implementation_review": "pending",
    }
    (rm / "registry.yaml").write_text(
        yaml.safe_dump({"version": 1, "entries": [entry]}), encoding="utf-8"
    )
    (project / ".gitignore").write_text("work/reviews/\n", encoding="utf-8")
    git(git_top, "add", "-A")
    git(git_top, "commit", "-qm", "graph")
    git(git_top, "checkout", "-q", "-b", "feature/rm-thing")
    commit_file(git_top, git_root_relative(git_top, project, "src/a.py"), "print('a')\n", "impl")
    commit_file(git_top, git_root_relative(git_top, project, "docs/x.md"), "# x\n", "stray")
    if shape == "nested_outside":
        commit_file(git_top, OUTSIDE_ROOT_FILE, "# outside\n", "outside root")
    return git_top.resolve(), project.resolve()


def prepare_layout_merge_mode_remote(
    git_top: Path, project: Path, tmp_path: Path
) -> Path:
    """Merge mode on ``dev``, feature branch merged with ``dev``, bare ``origin`` — repo stays on feature."""
    wf = git_root_relative(git_top, project, "roadmap/git-workflow.yaml")
    git(git_top, "checkout", "-q", "dev")
    commit_file(
        git_top,
        wf,
        "version: 1\nintegration_branch: dev\nremote: origin\non_complete: merge\n",
        "merge mode",
    )
    gi = git_root_relative(git_top, project, ".gitignore")
    commit_file(git_top, gi, "work/reviews/\n.specyrd/cache/\n", "gitignore")
    git(git_top, "checkout", "-q", "feature/rm-thing")
    git(git_top, "merge", "-q", "--no-edit", "dev")
    bare = tmp_path / "remote.git"
    tmp_path.mkdir(parents=True, exist_ok=True)
    git(tmp_path, "clone", "-q", "--bare", str(git_top), str(bare))
    git(bare, "symbolic-ref", "HEAD", "refs/heads/dev")
    git(git_top, "remote", "add", "origin", str(bare))
    git(git_top, "fetch", "-q", "origin")
    return bare


def make_review_repo(tmp_path: Path, *, orchestration: str | None = None) -> Path:
    root = tmp_path / "r"
    (root / "roadmap" / "phases").mkdir(parents=True)
    git(root, "init", "-q", "-b", "dev")
    git(root, "config", "user.email", "t@e.com")
    git(root, "config", "user.name", "T")
    # validate (run by pickup and CRUD) reads the consumer's schemas/.
    shutil.copytree(DOGFOOD / "schemas", root / "schemas")
    rm = root / "roadmap"
    (rm / "manifest.json").write_text(
        json.dumps({"version": 1, "includes": ["phases/M1.json"]}), encoding="utf-8"
    )
    (rm / "phases" / "M1.json").write_text(json.dumps({"nodes": [NODE]}), encoding="utf-8")
    sheet = root / NODE["planning_dir"]
    sheet.parent.mkdir(parents=True)
    sheet.write_text("# M1.1 Thing\n\n## Intent\n\nDo the thing.\n\n## References\n", encoding="utf-8")
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
