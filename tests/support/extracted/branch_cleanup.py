"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

from pathlib import Path
from tests.helpers import REPO
from tests.support.review import commit_file, git
from tests.support.review import make_review_repo

BR = "feature/rm-thing"

def _merge_mode_repo(tmp_path: Path, monkeypatch) -> tuple[Path, Path]:
    """The claimed leaf, mergeable into ``dev``, with a bare origin holding both branches."""
    monkeypatch.setenv("PYTHONPATH", str(REPO))   # finish runs validate/export/digest as subprocesses
    repo = make_review_repo(tmp_path)
    git(repo, "checkout", "-q", "dev")
    commit_file(repo, "roadmap/git-workflow.yaml",
                "version: 1\nintegration_branch: dev\nremote: origin\non_complete: merge\n", "merge mode")
    commit_file(repo, ".gitignore", "work/reviews/\n.specyrd/cache/\n", "as init project scaffolds")
    git(repo, "checkout", "-q", BR)
    git(repo, "merge", "-q", "--no-edit", "dev")
    bare = tmp_path / "remote.git"
    git(tmp_path, "clone", "-q", "--bare", str(repo), str(bare))
    git(bare, "symbolic-ref", "HEAD", "refs/heads/dev")   # a remote refuses to delete its HEAD branch
    git(repo, "remote", "add", "origin", str(bare))
    git(repo, "fetch", "-q", "origin")
    git(repo, "remote", "set-head", "origin", "dev")   # as clone does; fetch does it only from git 2.48
    return repo, bare
