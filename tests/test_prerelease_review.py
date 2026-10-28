"""Pre-release review findings: review-gate trust and eligibility, plan pools, the CLI prompt channel."""

from __future__ import annotations

import subprocess
from pathlib import Path

from tests.review_repo_helpers import NODE, commit_file, git, make_review_repo, review_text

from specy_road.review_files import reviews_dir
from specy_road.review_gate import evaluate_gate, policy_source, review_required

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


SENSITIVE = """version: 1
roster:
  - {id: human, family: human, roles: [coordinator]}
  - {id: pub, family: openai, roles: [reviewer]}
  - {id: sub, family: google, roles: [executor]}
  - {id: wide, family: anthropic, roles: [reviewer], may_process: [public, restricted]}
policy: {reviewers_required: 2}
substitutions:
  - {slot: rev, use: sub, decided: 2026-01-01, expires: 2027-01-01}
"""


def test_a_public_only_reviewer_cannot_approve_a_restricted_node(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path, orchestration=SENSITIVE)
    git(repo, "update-ref", "refs/heads/dev", "HEAD")
    head = git(repo, "rev-parse", "HEAD")
    d = reviews_dir(repo, "M1.1")
    d.mkdir(parents=True)
    for model in ("pub", "sub", "wide"):
        (d / f"REVIEW-{model}.md").write_text(review_text(head, model=model))
    gate = evaluate_gate(repo, {**NODE, "sensitivity": "restricted"}, head)
    assert [a.model for a in gate.approvals] == ["wide"] and not gate.passed
    assert sorted(r.path.name for r, why in gate.ineligible if "may process only" in why) == [
        "REVIEW-pub.md", "REVIEW-sub.md"]
    assert evaluate_gate(repo, NODE, head).passed   # the same records count on a public node

