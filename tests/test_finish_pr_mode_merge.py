"""M11.52: under ``on_complete: pr`` finish merges the integration tip in when only bookkeeping conflicts.

Both cases move ``dev`` on the remote from a second clone, as pickup does in
another lane, and leave this checkout's ``origin/dev`` stale: the preflight
trial merge cannot see the change, so only the check after the bookkeeping
commit can.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

from specy_road.bundled_scripts import finish_task
from tests.helpers import REPO
from tests.review_repo_helpers import (
    commit_file,
    git,
    git_root_relative,
    make_layout_finish_repo,
    prepare_layout_merge_mode_remote,
)

BR = "feature/rm-thing"
OTHER = {"codename": "other", "node_id": "M1.2", "branch": "feature/rm-other",
         "touch_zones": ["lib"], "implementation_review": "pending"}


@pytest.fixture(params=["embedded", "nested"])
def lane(request, tmp_path, monkeypatch) -> tuple[Path, Path, Path, str]:
    """``(git_top, project, bare, prefix)``: a claimed leaf with a bare ``origin`` whose ``dev`` is ours."""
    monkeypatch.setenv("PYTHONPATH", str(REPO))
    git_top, project = make_layout_finish_repo(tmp_path / "lane", request.param)
    bare = prepare_layout_merge_mode_remote(git_top, project, tmp_path / "lane")
    return git_top, project, bare, git_root_relative(git_top, project, "")


def _push_to_dev(tmp_path: Path, bare: Path, rel: str, edit) -> None:
    """Commit ``edit(old text)`` at ``rel`` on ``dev`` from another clone and push it."""
    other = tmp_path / "other-lane"
    git(tmp_path, "clone", "-q", "-b", "dev", str(bare), str(other))
    git(other, "config", "user.email", "o@e.com")
    git(other, "config", "user.name", "O")
    path = other / rel
    old = path.read_text(encoding="utf-8") if path.is_file() else ""
    commit_file(other, rel, edit(old), "another lane")
    git(other, "push", "-q", "origin", "dev")


def _finish(project: Path) -> int:
    with pytest.raises(SystemExit) as exc:
        finish_task.main(["--repo-root", str(project), "--on-complete", "pr", "--push"])
        raise SystemExit(0)
    return exc.value.code or 0


def _with_other_claim(text: str) -> str:
    doc = yaml.safe_load(text)
    doc["entries"].append(OTHER)
    return yaml.safe_dump(doc)


def test_claim_gained_after_pickup_is_resolved_and_the_branch_merges_cleanly(lane, tmp_path, capsys) -> None:
    git_top, project, bare, prefix = lane
    reg = prefix + "roadmap/registry.yaml"
    _push_to_dev(tmp_path, bare, reg, _with_other_claim)

    assert _finish(project) == 0
    out = capsys.readouterr().out
    assert f"[ok] merged refs/remotes/origin/dev into {BR}: resolved roadmap/registry.yaml" in out

    pushed = git(bare, "rev-parse", BR)
    assert pushed == git(git_top, "rev-parse", "HEAD")
    assert git(bare, "rev-parse", f"{BR}^2") == git(bare, "rev-parse", "dev")
    entries = yaml.safe_load(git(bare, "show", f"{BR}:{reg}"))["entries"]
    assert [e["codename"] for e in entries] == ["other"]
    # The PR merges without a conflict, and the result keeps the other lane's claim.
    tree = subprocess.run(["git", "-C", str(bare), "merge-tree", "--write-tree", "dev", BR],
                          capture_output=True, text=True, check=False)
    assert tree.returncode == 0, tree.stdout
    merged = yaml.safe_load(git(bare, "show", f"{tree.stdout.split()[0]}:{reg}"))["entries"]
    assert [e["codename"] for e in merged] == ["other"]
    # The generated files were rendered from the merged registry, so the other claim is listed.
    assert "M1.2" in (project / "roadmap-context.md").read_text(encoding="utf-8")
    assert git(git_top, "status", "--porcelain", "--untracked-files=no") == ""


def test_code_conflict_is_named_and_nothing_is_pushed(lane, tmp_path, capsys) -> None:
    git_top, project, bare, prefix = lane
    _push_to_dev(tmp_path, bare, prefix + "src/a.py", lambda _old: "print('dev')\n")
    before = git(bare, "rev-parse", BR)

    assert _finish(project) == 1
    err = capsys.readouterr().err
    assert f"error: the PR into dev would conflict: merging refs/remotes/origin/dev into {BR} " \
           "conflicts on src/a.py. Nothing was pushed." in err
    assert git(bare, "rev-parse", BR) == before
    # The bookkeeping commit stays as the tip, with no merge left half-done.
    assert git(git_top, "log", "-1", "--format=%s") == "chore(rm-thing): complete, deregister"
    assert subprocess.run(["git", "-C", str(git_top), "rev-parse", "-q", "--verify", "MERGE_HEAD"],
                          capture_output=True, check=False).returncode != 0
