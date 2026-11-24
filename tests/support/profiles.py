"""A review repo with a roster entry backed by the shipped claude-opus-5-5 model profile."""

from __future__ import annotations

import shutil
from pathlib import Path

from tests.helpers import REPO
from tests.support.review import make_review_repo, git

TEMPLATE_PROFILES = REPO / "specy_road" / "templates" / "project" / "model-profiles"
OPUS = TEMPLATE_PROFILES / "anthropic-claude" / "claude-opus-5-5.md"

ROSTER = """version: 1
roster:
  - {id: human, family: human, roles: [coordinator, reviewer]}
  - id: opus
    family: anthropic
    profile: model-profiles/anthropic-claude/claude-opus-5-5.md
    roles: [coordinator, executor, reviewer]
  - {id: sol, family: openai, roles: [reviewer]}
"""


def make_profile_repo(tmp_path: Path) -> Path:
    """:func:`make_review_repo` with :data:`ROSTER` and the opus profile, both landed on ``dev``."""
    repo = make_review_repo(tmp_path, orchestration=ROSTER)
    dest = repo / "model-profiles" / "anthropic-claude"
    dest.mkdir(parents=True)
    shutil.copy(OPUS, dest / OPUS.name)
    git(repo, "add", "model-profiles", "roadmap/orchestration.yaml")
    git(repo, "commit", "-qm", "roster + profile")
    git(repo, "checkout", "-q", "dev")
    git(repo, "merge", "-q", "feature/rm-thing")
    git(repo, "checkout", "-q", "feature/rm-thing")
    return repo


def commit_profile(repo: Path) -> None:
    """Profiles are read from the integration branch: land the edit on ``dev``."""
    git(repo, "commit", "-qam", "profile edit")
    git(repo, "update-ref", "refs/heads/dev", "HEAD")
