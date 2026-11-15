"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

from tests.helpers import DOGFOOD
from pathlib import Path
import json
from specy_road.roadmap_layout import natural_id_sort_key
import pytest
import shutil
import subprocess

def git(args: list[str], cwd: Path) -> str:
    """Shared test helper."""
    out = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
        env={
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@example.com",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@example.com",
            "PATH": "/usr/bin:/bin:/usr/local/bin",
            "HOME": str(cwd),
        },
    )
    return out.stdout.strip()

@pytest.fixture()
def autoff_repo(tmp_path: Path) -> tuple[Path, Path]:
    """Bare remote + working tree where remote is 2 commits ahead of HEAD.

    Returns ``(working_tree, bare_remote)``. ``integration_branch=master``
    is set in ``roadmap/git-workflow.yaml`` so
    ``maybe_auto_integration_ff`` will engage without depending on the
    toolkit's default ``main`` branch.
    """
    work = tmp_path / "work"
    shutil.copytree(DOGFOOD, work)
    bare = tmp_path / "remote.git"
    # -b master: the bare repo's HEAD has to name the one branch this
    # fixture ever pushes. Left to the git build's init.defaultBranch it
    # can point at main, and the clone below then lands on an unborn
    # main with no local master to push.
    git(["init", "--bare", "-q", "-b", "master", str(bare)], tmp_path)
    git(["init", "-q", "-b", "master"], work)
    git(["add", "-A"], work)
    git(["commit", "-q", "-m", "initial"], work)
    gw = work / "roadmap" / "git-workflow.yaml"
    gw.write_text(
        gw.read_text(encoding="utf-8").replace(
            "integration_branch: main", "integration_branch: master"
        ),
        encoding="utf-8",
    )
    git(["commit", "-q", "-am", "use master"], work)
    git(["remote", "add", "origin", str(bare)], work)
    git(["push", "-q", "-u", "origin", "master"], work)
    helper = tmp_path / "helper"
    git(["clone", "-q", str(bare), str(helper)], tmp_path)
    git(["commit", "-q", "--allow-empty", "-m", "ahead-1"], helper)
    git(["commit", "-q", "--allow-empty", "-m", "ahead-2"], helper)
    git(["push", "-q", "origin", "master"], helper)
    return work, bare

def siblings_of(work: Path, parent: str) -> list[str]:
    """Shared test helper."""
    out: list[tuple[int, str]] = []
    for chunk in (work / "roadmap" / "phases").glob("*.json"):
        doc = json.loads(chunk.read_text(encoding="utf-8"))
        for n in doc.get("nodes") or []:
            if n.get("parent_id") == parent:
                out.append((int(n.get("sibling_order", 0)), str(n["id"])))
    out.sort(key=lambda t: (t[0], natural_id_sort_key(t[1])))
    return [k for _, k in out]
