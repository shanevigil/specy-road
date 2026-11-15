"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

from tests.support.review import NODE, git
from pathlib import Path
from tests.support.review import commit_file
import json
from tests.support.review import make_review_repo
import pytest
import shutil
import yaml

TOOLKIT_STASH = "specy-road: temp stash work/ around pickup"

def _branch_with_commits(repo: Path, branch: str, *rels: str) -> None:
    git(repo, "checkout", "-q", "-b", branch, "dev")
    for rel in rels:
        commit_file(repo, rel, f"{rel}\n", rel)
    git(repo, "checkout", "-q", "dev")

def _graph_and_registry(repo: Path) -> None:
    """Complete leaves ``finished`` and ``settled`` (still registered), an open rollup
    ``roll``, a claim ``ghost`` with no branch."""
    chunk = repo / "roadmap" / "phases" / "M1.json"
    doc = json.loads(chunk.read_text())
    doc["nodes"][0]["milestone_execution"] = {"state": "active", "rollup_branch": "feature/rm-roll"}
    doc["nodes"].append({**NODE, "id": "M1.2", "codename": "finished", "status": "Complete",
                         "node_key": "22222222-2222-5222-8222-222222222222", "sibling_order": 2})
    doc["nodes"].append({**NODE, "id": "M1.4", "codename": "settled", "status": "Complete",
                         "node_key": "44444444-4444-5444-8444-444444444444", "sibling_order": 4})
    commit_file(repo, "roadmap/phases/M1.json", json.dumps(doc), "graph")
    reg = yaml.safe_load((repo / "roadmap" / "registry.yaml").read_text())
    for codename, node_id in (("ghost", "M1.3"), ("settled", "M1.4")):
        reg["entries"].append({"codename": codename, "node_id": node_id,
                               "branch": f"feature/rm-{codename}", "touch_zones": [codename]})
    commit_file(repo, "roadmap/registry.yaml", yaml.safe_dump(reg), "claims")

@pytest.fixture
def doctor_repo(tmp_path: Path, monkeypatch) -> tuple[Path, Path]:
    repo = make_review_repo(tmp_path)
    git(repo, "checkout", "-q", "dev")
    _graph_and_registry(repo)
    git(repo, "branch", "feature/rm-roll")
    for name in ("done", "rebased", "finished", "open", "gone", "settled"):
        _branch_with_commits(repo, f"feature/rm-{name}", f"src/{name}.py")
    _branch_with_commits(repo, "feature/rm-squash", "src/s1.py", "src/s2.py")
    for branch in ("feature/rm-done", "feature/rm-gone", "feature/rm-thing", "feature/rm-settled"):
        git(repo, "merge", "-q", "--no-ff", "--no-edit", branch)
    git(repo, "merge", "-q", "--squash", "feature/rm-squash")
    git(repo, "commit", "-qm", "squash")
    git(repo, "cherry-pick", "feature/rm-rebased")   # same patch, new sha
    bare = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", str(bare))
    git(bare, "symbolic-ref", "HEAD", "refs/heads/dev")
    git(repo, "remote", "add", "origin", str(bare))
    git(repo, "push", "-q", "origin", "--all")
    git(repo, "branch", "-q", "-D", "feature/rm-gone")

    git(repo, "worktree", "add", "-q", str(tmp_path / "wt-done"), "feature/rm-done")
    (tmp_path / "wt-done" / "work" / "reviews").mkdir(parents=True)
    (tmp_path / "wt-done" / "work" / "reviews" / "READY.md").write_text("x", encoding="utf-8")
    git(repo, "worktree", "add", "-q", "--detach", str(tmp_path / "wt-detached"), "dev")
    git(repo, "worktree", "add", "-q", "--detach", str(tmp_path / "wt-squash"), "feature/rm-squash")
    git(repo, "worktree", "add", "-q", str(tmp_path / "wt-missing"), "feature/rm-squash")
    shutil.rmtree(tmp_path / "wt-missing")
    git(repo, "worktree", "add", "-q", str(tmp_path / "wt-thing"), "feature/rm-thing")
    git(repo, "worktree", "add", "-q", str(tmp_path / "wt-settled"), "feature/rm-settled")
    git(repo, "worktree", "add", "-q", "--detach", str(tmp_path / "wt-wip"), "feature/rm-open")
    (tmp_path / "wt-wip" / "src" / "wip.py").write_text("unsaved\n", encoding="utf-8")
    git(repo, "worktree", "add", "-q", "--detach", str(tmp_path / "wt-locked"), "dev")
    git(repo, "worktree", "lock", str(tmp_path / "wt-locked"))

    for msg in (TOOLKIT_STASH, "mine"):
        (repo / "work").mkdir(exist_ok=True)
        (repo / "work" / "note.md").write_text(msg, encoding="utf-8")
        git(repo, "stash", "push", "-q", "-u", "-m", msg)
    return repo, bare
