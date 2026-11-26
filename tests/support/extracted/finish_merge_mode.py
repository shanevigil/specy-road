"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

from pathlib import Path
from tests.helpers import REPO
from tests.support.same.commit_553cf5f7a1bf import commit
from tests.support.same.git_df16ee62bf81 import git as git_cmd
from tests.support.review import commit_file, git
from tests.support.review import make_review_repo
import subprocess

def bootstrap(tmp_path: Path) -> tuple[Path, Path]:
    """Init a sandbox repo with a bare 'origin', and master + feature branches."""
    bare = tmp_path / "remote.git"
    subprocess.check_call(["git", "init", "--bare", "-q", str(bare)])
    repo = tmp_path / "work"
    subprocess.check_call(["git", "init", "-q", "-b", "master", str(repo)])
    git_cmd(repo, "config", "user.email", "t@e.com")
    git_cmd(repo, "config", "user.name", "T")
    git_cmd(repo, "remote", "add", "origin", str(bare))
    commit(repo, "init")
    git_cmd(repo, "push", "-q", "-u", "origin", "master")
    git_cmd(repo, "checkout", "-b", "feature/rm-x")
    commit(repo, "feature work")
    git_cmd(repo, "push", "-q", "-u", "origin", "feature/rm-x")
    return repo, bare

def merge_mode_finish_repo(tmp_path: Path, monkeypatch) -> tuple[Path, Path]:
    monkeypatch.setenv("PYTHONPATH", str(REPO))
    repo = make_review_repo(tmp_path)
    git(repo, "checkout", "-q", "dev")
    commit_file(
        repo,
        "roadmap/git-workflow.yaml",
        "version: 1\nintegration_branch: dev\nremote: origin\non_complete: merge\n",
        "merge mode",
    )
    commit_file(repo, ".gitignore", "work/reviews/\n.specyrd/cache/\n", "gitignore")
    git(repo, "checkout", "-q", "feature/rm-thing")
    git(repo, "merge", "-q", "--no-edit", "dev")
    bare = tmp_path / "remote.git"
    git(tmp_path, "clone", "-q", "--bare", str(repo), str(bare))
    git(bare, "symbolic-ref", "HEAD", "refs/heads/dev")
    git(repo, "remote", "add", "origin", str(bare))
    git(repo, "fetch", "-q", "origin")
    git(repo, "remote", "set-head", "origin", "dev")   # as clone does; fetch does it only from git 2.48
    return repo, bare
