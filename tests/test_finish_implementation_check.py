"""A claim is not an implementation (finding 32)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from specy_road.finish_implementation_check import (
    implementation_gate_error,
    implementation_paths,
    zone_matches,
)


# ---------------------------------------------------------------------------
# Zone matching
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "zone,path,expected",
    [
        ("src/api", "src/api/routes.py", True),
        ("src/api", "src/api", True),
        ("src/api", "src/apixyz/routes.py", False),
        ("src/api", "docs/readme.md", False),
        ("src/api/routes.py", "src/api/routes.py", True),
        ("docs", "docs/guide.md", True),
        # fnmatch does not treat "/" specially, and that leniency is deliberate.
        ("src/*", "src/api/routes.py", True),
        ("*.md", "README.md", True),
        ("src/**/*.py", "src/api/routes.py", True),
    ],
)
def test_zone_matching(zone, path, expected):
    assert zone_matches(zone, path) is expected


# ---------------------------------------------------------------------------
# Against a real git repo
# ---------------------------------------------------------------------------


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "Test")
    (root / "seed.txt").write_text("seed", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-m", "seed")
    _git(root, "checkout", "-b", "feature/rm-cn")
    return root


def _commit(repo: Path, rel: str, body: str = "x") -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", f"add {rel}")


def _paths(repo: Path, zones):
    return implementation_paths(
        repo, zones=zones, remote="origin", integration_branch="main"
    )


def _error(repo: Path, zones):
    return implementation_gate_error(
        repo, node_id="M1.1", zones=zones, remote="origin", integration_branch="main"
    )


def test_work_inside_the_zone_passes(repo):
    _commit(repo, "src/api/routes.py")

    assert _paths(repo, ["src/api"]) == ["src/api/routes.py"]
    assert _error(repo, ["src/api"]) is None


def test_an_untouched_branch_is_refused(repo):
    assert _paths(repo, ["src/api"]) == []
    error = _error(repo, ["src/api"])
    assert error is not None
    assert "nothing was implemented for M1.1" in error
    assert "--allow-empty-implementation" in error
    assert "abort-task-pickup" in error


def test_work_outside_every_zone_is_refused(repo):
    """The registration-only case: commits exist, none of them are the task."""
    _commit(repo, "notes/scratch.md")

    assert _paths(repo, ["src/api"]) == []
    assert _error(repo, ["src/api"]) is not None


def test_a_docs_only_leaf_still_satisfies_its_own_zone(repo):
    """Small leaves are the false-positive risk; each still writes in its zone."""
    _commit(repo, "docs/guide.md")

    assert _error(repo, ["docs"]) is None


def test_any_one_zone_is_enough(repo):
    _commit(repo, "src/api/routes.py")

    assert _error(repo, ["src/api", "web/ui", "infra"]) is None


def test_no_declared_zones_means_nothing_to_check(repo):
    """touch_zones are optional (F-009); absence is not evidence of idleness."""
    assert _paths(repo, []) is None
    assert _error(repo, []) is None
    assert _error(repo, ["   ", ""]) is None


def test_an_unresolvable_base_allows_the_finish(repo):
    """Cannot-tell must read as allow, or an odd clone cannot finish at all."""
    result = implementation_gate_error(
        repo, node_id="M1.1", zones=["src/api"],
        remote="origin", integration_branch="no-such-branch",
    )
    assert result is None


def test_outside_a_worktree_allows_the_finish(tmp_path):
    assert implementation_gate_error(
        tmp_path, node_id="M1.1", zones=["src/api"],
        remote="origin", integration_branch="main",
    ) is None


def test_commits_that_landed_on_main_afterwards_are_not_this_branchs_work(repo):
    """`...` diffs from the merge base, so main moving on does not count."""
    _git(repo, "checkout", "main")
    _commit(repo, "src/api/someone_else.py")
    _git(repo, "checkout", "feature/rm-cn")

    assert _paths(repo, ["src/api"]) == []
    assert _error(repo, ["src/api"]) is not None


def test_the_remote_tracking_ref_is_preferred_over_a_stale_local(repo):
    """A clone that has been picking work up for a while has a stale local base."""
    _commit(repo, "src/api/routes.py")
    _git(repo, "update-ref", "refs/remotes/origin/main", "main")
    _git(repo, "checkout", "main")
    _commit(repo, "src/api/later.py")
    _git(repo, "checkout", "feature/rm-cn")

    assert _paths(repo, ["src/api"]) == ["src/api/routes.py"]
