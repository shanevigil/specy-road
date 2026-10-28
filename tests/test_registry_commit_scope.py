"""Registry commits touch only the registry, and nothing stashes ``work/``.

Pickup used to stash ``work/`` (untracked files included) around the
integration-branch registry commit and pop it afterwards. The stash stack is
shared by every session in a checkout, so files another session wrote during
that window were stranded in the stash, and a failed pop only warned.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from specy_road.bundled_scripts.do_next_task_pickup_helpers import register_and_commit
from specy_road.bundled_scripts.repo_ops import working_tree_clean


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True).stdout


def _repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@e.com")
    _git(tmp_path, "config", "user.name", "T")
    (tmp_path / "roadmap").mkdir()
    (tmp_path / "roadmap" / "registry.yaml").write_text("version: 1\nentries: []\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "init")
    return tmp_path


def test_work_changes_do_not_count_against_a_clean_tree_when_asked(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "work").mkdir()
    (repo / "work" / "brief-M1.1.md").write_text("brief\n", encoding="utf-8")

    assert not working_tree_clean(repo)
    assert working_tree_clean(repo, except_work=True)

    (repo / "README.md").write_text("x\n", encoding="utf-8")
    assert not working_tree_clean(repo, except_work=True)


def test_the_registry_commit_carries_only_the_registry(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "work").mkdir()
    (repo / "work" / "staged.md").write_text("someone else's\n", encoding="utf-8")
    (repo / "work" / "untracked.md").write_text("live session file\n", encoding="utf-8")
    _git(repo, "add", "work/staged.md")

    register_and_commit(
        registry_path=repo / "roadmap" / "registry.yaml",
        git_runner=lambda *a: _git(repo, *a),
        node={"id": "M1.1", "codename": "first"},
        branch="feature/rm-first",
        reg={"version": 1, "entries": []},
        commit_message="chore: claim M1.1",
        impl_review_gate=False,
    )

    assert _git(repo, "show", "--name-only", "--format=", "HEAD").split() == ["roadmap/registry.yaml"]
    assert "A  work/staged.md" in _git(repo, "status", "--porcelain")
    assert (repo / "work" / "untracked.md").read_text(encoding="utf-8") == "live session file\n"
    assert _git(repo, "stash", "list") == ""
