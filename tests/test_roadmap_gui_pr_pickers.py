"""Unit tests for GitHub/GitLab PR/MR row selection helpers."""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent.parent / "specy_road" / "bundled_scripts"
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from roadmap_gui_pr_pickers import (  # noqa: E402
    github_pulls_for_branch,
    gitlab_mrs_for_branch,
    pick_latest_github_pr,
    pick_latest_gitlab_mr,
)


def test_github_pulls_for_branch_prefers_head_ref() -> None:
    pulls = [
        {"head": {"ref": "other"}, "updated_at": "2025-01-02T00:00:00Z"},
        {"head": {"ref": "feature/rm-x"}, "updated_at": "2025-01-01T00:00:00Z"},
    ]
    scoped = github_pulls_for_branch(pulls, "feature/rm-x")
    assert len(scoped) == 1
    assert scoped[0]["head"]["ref"] == "feature/rm-x"


def test_pick_latest_github_pr_by_updated_at() -> None:
    pulls = [
        {"updated_at": "2025-01-01T00:00:00Z", "number": 1},
        {"updated_at": "2025-03-01T00:00:00Z", "number": 2},
    ]
    assert pick_latest_github_pr(pulls)["number"] == 2


def test_gitlab_mrs_for_branch_prefers_source_branch() -> None:
    mrs = [
        {"source_branch": "other", "updated_at": "2025-02-01T00:00:00Z"},
        {"source_branch": "feature/rm-y", "updated_at": "2025-01-01T00:00:00Z"},
    ]
    scoped = gitlab_mrs_for_branch(mrs, "feature/rm-y")
    assert len(scoped) == 1
    assert scoped[0]["source_branch"] == "feature/rm-y"


def test_pick_latest_gitlab_mr_by_updated_at() -> None:
    mrs = [
        {"updated_at": "2025-01-01T00:00:00Z", "iid": 1},
        {"updated_at": "2025-04-01T00:00:00Z", "iid": 2},
    ]
    assert pick_latest_gitlab_mr(mrs)["iid"] == 2
