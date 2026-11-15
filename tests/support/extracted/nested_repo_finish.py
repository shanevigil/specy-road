"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

from tests.support.extracted.nested_repo_worktrees import COVERED
from pathlib import Path
from tests.support.extracted.nested_repo_worktrees import add_nested_repo
from tests.support.review import commit_file, git
from specy_road.finish_land_integration import land_merge_feature_into_integration
from tests.support.review import make_review_repo

BRANCH = "feature/rm-thing"

def repos(tmp_path: Path, *rels: str, text: str = "x = 2\n") -> tuple[Path, list[Path]]:
    """``(repo on the feature branch, each nested repo on dev with the leaf branch committed)``; the leaf's
    ``core.py`` is ``text``, prefixed with the repository's path so each diff is its own."""
    repo = make_review_repo(tmp_path)
    git(repo, "checkout", "-q", "dev")
    nested = [add_nested_repo(repo, rel, "dev") for rel in rels]
    git(repo, "checkout", "-q", BRANCH)
    git(repo, "merge", "-q", "--no-edit", "dev")
    bare = tmp_path / "remote.git"
    git(tmp_path, "clone", "-q", "--bare", str(repo), str(bare))
    git(repo, "remote", "add", "origin", str(bare))
    git(repo, "fetch", "-q", "origin")
    for rel, n in zip(rels, nested):
        git(n, "checkout", "-q", "-b", BRANCH)
        commit_file(n, "core.py", (f"# {rel}\n" if len(rels) > 1 else "") + text, "leaf work in the nested repo")
        git(n, "checkout", "-q", "dev")
    return repo, nested

def repo(tmp_path: Path, rel: str = COVERED, text: str = "x = 2\n") -> tuple[Path, Path]:
    """Shared test helper."""
    repo, (nested,) = repos(tmp_path, rel, text=text)
    return repo, nested

def origin_tip(repo: Path, branch: str = "dev") -> str:
    """Shared test helper."""
    return git(repo, "ls-remote", "origin", f"refs/heads/{branch}").split()[0]

def land(repo: Path) -> tuple[bool, str]:
    """Shared test helper."""
    return land_merge_feature_into_integration(repo, remote="origin", integration_branch="dev",
                                               feature_branch=BRANCH, land_check_cmd="")
