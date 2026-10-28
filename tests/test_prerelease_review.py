"""Pre-release review findings: review-gate trust and eligibility, plan pools, the CLI prompt channel."""

from __future__ import annotations

import subprocess
from pathlib import Path

from tests.review_repo_helpers import commit_file, git, make_review_repo

from specy_road.review_gate import policy_source, review_required

ROSTER = """version: 1
roster:
  - {id: human, family: human, roles: [coordinator, reviewer]}
policy: {reviewers_required: 1}
"""
SELF_NOMINATED = "version: 1\nintegration_branch: feature/rm-thing\nremote: {remote}\n"


def test_a_feature_branch_cannot_nominate_itself_as_the_integration_branch(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path, orchestration=ROSTER)
    bare = tmp_path / "remote.git"
    subprocess.run(["git", "clone", "-q", "--bare", str(repo), str(bare)], check=True)
    git(bare, "symbolic-ref", "HEAD", "refs/heads/dev")
    git(repo, "remote", "add", "origin", str(bare))
    git(repo, "fetch", "-q", "origin")
    git(repo, "remote", "set-head", "origin", "--auto")
    # self-named, review switched off, and pushed: the remote's default branch still names dev
    commit_file(repo, "roadmap/git-workflow.yaml", SELF_NOMINATED.format(remote="origin"), "self")
    git(repo, "push", "-q", "origin", "feature/rm-thing")
    assert policy_source(repo) == ("refs/remotes/origin/dev", None)
    assert review_required(repo)
    # pointing at a remote that is not configured does not make this a local-only repo
    commit_file(repo, "roadmap/git-workflow.yaml", SELF_NOMINATED.format(remote="nosuch"), "no remote")
    ref, err = policy_source(repo)
    assert ref is None and "'nosuch'" in err and "not configured" in err
    assert review_required(repo)
