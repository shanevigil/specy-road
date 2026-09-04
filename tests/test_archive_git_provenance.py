"""Archive records capture the refs the work was delivered on.

Every field is best-effort by design — a repo with no rollup history, deleted
branches, or no tags must still archive cleanly. These tests cover both ends:
a real merge where the refs resolve, and the degenerate cases where they don't.

Nothing here may create git objects; archiving only reads refs.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from specy_road.archive_git import capture_provenance, merge_commit_for, nearest_tag

_ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.com",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.com",
}


def _git(repo: Path, *args: str) -> str:
    import os

    env = os.environ.copy()
    env.update(_ENV)
    r = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )
    return r.stdout.strip()


@pytest.fixture()
def delivered(tmp_path: Path) -> Path:
    """A repo where `rollup/M1` was merged into `main` and then tagged."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    (repo / "f.txt").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")

    _git(repo, "checkout", "-q", "-b", "rollup/M1")
    (repo / "f.txt").write_text("work\n", encoding="utf-8")
    _git(repo, "commit", "-q", "-am", "milestone work")

    _git(repo, "checkout", "-q", "main")
    _git(repo, "merge", "-q", "--no-ff", "-m", "merge rollup/M1", "rollup/M1")
    _git(repo, "tag", "v1.2.0")
    (repo / "f.txt").write_text("later\n", encoding="utf-8")
    _git(repo, "commit", "-q", "-am", "unrelated later work")
    return repo


def _node(**me) -> dict:
    return {
        "id": "M1",
        "milestone_execution": {
            "state": "closed",
            "rollup_branch": "rollup/M1",
            "integration_branch": "main",
            "remote": "origin",
            "closed_at": "2026-01-01T00:00:00+00:00",
            **me,
        },
    }


def test_it_finds_the_merge_that_landed_the_work(delivered: Path) -> None:
    got = capture_provenance(delivered, _node())

    expected = _git(delivered, "rev-list", "--merges", "-1", "main")
    assert got["merge_commit"] == expected
    assert got["rollup_tip"] == _git(delivered, "rev-parse", "rollup/M1")
    assert got["rollup_branch"] == "rollup/M1"
    assert got["integration_branch"] == "main"
    assert got["closed_at"] == "2026-01-01T00:00:00+00:00"


def test_it_records_the_nearest_tag_from_the_merge(delivered: Path) -> None:
    assert capture_provenance(delivered, _node())["nearest_tag"] == "v1.2.0"


def test_it_creates_no_git_objects(delivered: Path) -> None:
    before = _git(delivered, "rev-parse", "main"), _git(delivered, "tag", "-l")
    capture_provenance(delivered, _node())
    assert (_git(delivered, "rev-parse", "main"), _git(delivered, "tag", "-l")) == before


def test_a_deleted_rollup_branch_degrades_to_nulls(delivered: Path) -> None:
    _git(delivered, "branch", "-D", "rollup/M1")
    got = capture_provenance(delivered, _node())

    assert got["rollup_tip"] is None
    assert got["merge_commit"] is None
    assert got["rollup_branch"] == "rollup/M1"  # the name is still on record


def test_a_node_with_no_rollup_history_yields_a_full_null_block(delivered: Path) -> None:
    """Shape stays stable so readers never distinguish absent from unresolvable."""
    got = capture_provenance(delivered, {"id": "M1"})

    assert set(got) == {
        "rollup_branch",
        "integration_branch",
        "rollup_tip",
        "merge_commit",
        "nearest_tag",
        "closed_at",
    }
    assert all(v is None for v in got.values())


def test_an_untagged_repo_reports_no_tag(tmp_path: Path) -> None:
    repo = tmp_path / "bare-history"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    (repo / "f.txt").write_text("x\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "only")

    assert nearest_tag(repo, "main") is None


def test_provenance_on_a_directory_that_is_not_a_repo(tmp_path: Path) -> None:
    """The PM GUI can point at a plain directory; that must not raise."""
    got = capture_provenance(tmp_path, _node())
    assert got["rollup_tip"] is None
    assert got["merge_commit"] is None


def test_merge_commit_for_ignores_merges_off_the_ancestry_path(
    delivered: Path,
) -> None:
    """An unrelated merge on the integration branch must not be mistaken for it."""
    _git(delivered, "checkout", "-q", "-b", "other")
    (delivered / "g.txt").write_text("other\n", encoding="utf-8")
    _git(delivered, "add", "-A")
    _git(delivered, "commit", "-q", "-m", "other work")
    _git(delivered, "checkout", "-q", "main")
    _git(delivered, "merge", "-q", "--no-ff", "-m", "merge other", "other")

    tip = _git(delivered, "rev-parse", "rollup/M1")
    head = _git(delivered, "rev-parse", "main")
    found = merge_commit_for(delivered, tip, head)

    assert found == _git(delivered, "rev-list", "--merges", "-1", "--grep", "rollup/M1", "main")
