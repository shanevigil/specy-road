"""Two lanes finishing against one integration branch must both land.

``roadmap/registry.yaml`` is a keyed collection landed by a text merge, which
either conflicts (leaving the finish half-done, the claim never cleared) or
succeeds while keeping a row a lane removed. These tests pin the resolved
post-condition instead: integration's registry minus the finishing row,
whatever the feature branch's stale copy happens to say.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from specy_road.finish_land_deterministic import (
    codename_from_branch,
    merge_feature_deterministically,
)
from specy_road.finish_land_integration import land_merge_feature_into_integration
from specy_road.registry_yaml import read_registry, registry_path, write_registry
from tests.test_finish_merge_mode import _bootstrap, _commit, _git


def _out(repo: Path, *args: str) -> str:
    """Stripped stdout of a git command, for asserting on repo state."""
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True
    ).stdout.strip()


def _entry(codename: str) -> dict:
    return {
        "codename": codename,
        "node_id": f"M1.{codename[0]}",
        "branch": f"feature/rm-{codename}",
        "touch_zones": ["src/"],
        "started": "2026-09-01",
    }


def _write_rows(repo: Path, *codenames: str) -> None:
    path = registry_path(repo)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_registry(path, {"version": 1, "entries": [_entry(c) for c in codenames]})


def _rows(repo: Path) -> set[str]:
    entries = read_registry(registry_path(repo)).get("entries") or []
    return {e["codename"] for e in entries}


def _seed(repo: Path, *codenames: str) -> None:
    """Put a registry with these claims on the integration branch and push it."""
    _write_rows(repo, *codenames)
    _commit(repo, "register claims")
    _git(repo, "push", "-q", "origin", "master")


def _lane(repo: Path, codename: str, *remaining: str) -> None:
    """Branch a lane off master and give it a bookkeeping commit."""
    _git(repo, "checkout", "-q", "master")
    _git(repo, "checkout", "-q", "-b", f"feature/rm-{codename}")
    _write_rows(repo, *remaining)
    _commit(repo, f"chore(rm-{codename}): complete, deregister")


def _land(repo: Path, codename: str) -> tuple[bool, str]:
    _git(repo, "checkout", "-q", f"feature/rm-{codename}")
    return land_merge_feature_into_integration(
        repo,
        remote="origin",
        integration_branch="master",
        feature_branch=f"feature/rm-{codename}",
    )


def test_two_lanes_finishing_different_leaves_both_land(tmp_path: Path) -> None:
    """The report's headline failure: concurrent finishes minutes apart."""
    repo, _bare = _bootstrap(tmp_path)
    _seed(repo, "alpha", "beta")
    # Both lanes branch from the same registry and each drops only its own row,
    # so each one's copy still claims the other's leaf is in flight.
    _lane(repo, "alpha", "beta")
    _lane(repo, "beta", "alpha")

    ok, err = _land(repo, "alpha")
    assert ok, err
    ok, err = _land(repo, "beta")
    assert ok, err

    _git(repo, "checkout", "-q", "master")
    assert _rows(repo) == set()


def test_the_stale_feature_copy_never_resurrects_a_row(tmp_path: Path) -> None:
    """Landed content is integration's, not the feature branch's snapshot.

    The dangerous half of the bug needs no conflict to appear: the feature
    branch's registry is stale by construction, so a merge that simply trusted
    it could revive a claim another lane cleared or drop one it registered.
    """
    repo, _bare = _bootstrap(tmp_path)
    _seed(repo, "alpha", "stale")
    _lane(repo, "alpha", "stale")  # feature copy still holds `stale`

    # Meanwhile integration moves on: `stale` is cleared, `gamma` registered.
    _git(repo, "checkout", "-q", "master")
    _write_rows(repo, "alpha", "gamma")
    _commit(repo, "another lane lands, and a new pickup registers")
    _git(repo, "push", "-q", "origin", "master")

    ok, err = _land(repo, "alpha")
    assert ok, err
    _git(repo, "checkout", "-q", "master")
    assert _rows(repo) == {"gamma"}


def test_a_conflicting_registry_is_resolved_and_the_merge_lands(
    tmp_path: Path, capsys
) -> None:
    repo, _bare = _bootstrap(tmp_path)
    _seed(repo, "alpha", "beta", "charlie")
    _lane(repo, "beta", "alpha", "charlie")
    # Integration removes the row adjacent to the one the lane removed, so a
    # plain text merge of these two registries conflicts.
    _git(repo, "checkout", "-q", "master")
    _write_rows(repo, "beta", "charlie")
    _commit(repo, "adjacent row removed on integration")
    _git(repo, "push", "-q", "origin", "master")

    ok, err = _land(repo, "beta")
    assert ok, err
    _git(repo, "checkout", "-q", "master")
    assert _rows(repo) == {"charlie"}
    assert _out(repo, "status", "--porcelain") == ""


def test_a_row_already_absent_is_not_an_error(tmp_path: Path) -> None:
    """A retried finish must not fail because its post-condition already holds."""
    repo, _bare = _bootstrap(tmp_path)
    _seed(repo, "alpha", "beta")
    _lane(repo, "alpha", "beta")
    _git(repo, "checkout", "-q", "master")
    _write_rows(repo, "beta")  # someone already cleared alpha here
    _commit(repo, "claim already released")
    _git(repo, "push", "-q", "origin", "master")

    ok, err = _land(repo, "alpha")
    assert ok, err
    _git(repo, "checkout", "-q", "master")
    assert _rows(repo) == {"beta"}


def test_a_conflict_outside_the_deterministic_paths_still_fails(
    tmp_path: Path,
) -> None:
    """F-012 is untouched: a real source conflict is still a hard failure."""
    repo, _bare = _bootstrap(tmp_path)
    _seed(repo, "alpha")
    _git(repo, "checkout", "-q", "-b", "feature/rm-alpha")
    (repo / "src.py").write_text("lane\n")
    _commit(repo, "lane edits source")
    _git(repo, "checkout", "-q", "master")
    (repo / "src.py").write_text("integration\n")
    _commit(repo, "integration edits the same source")
    _git(repo, "push", "-q", "origin", "master")
    before = _out(repo, "rev-parse", "master")

    ok, err = _land(repo, "alpha")
    assert ok is False
    assert err.startswith("git merge feature/rm-alpha into master failed")
    # Recovery must be complete: nothing half-merged, nothing moved.
    assert _out(repo, "rev-parse", "--abbrev-ref", "HEAD") == (
        "feature/rm-alpha"
    )
    assert _out(repo, "status", "--porcelain") == ""
    assert _out(repo, "rev-parse", "master") == before


def test_the_feature_merge_is_never_a_fast_forward(tmp_path: Path) -> None:
    """A ff would make the stale feature copy integration's tip verbatim."""
    repo, _bare = _bootstrap(tmp_path)
    _seed(repo, "alpha")
    _lane(repo, "alpha")
    ok, err = _land(repo, "alpha")
    assert ok, err
    _git(repo, "checkout", "-q", "master")
    assert _out(repo, "rev-parse", "-q", "--verify", "HEAD^2")


def test_a_repo_without_a_registry_still_merges(tmp_path: Path) -> None:
    repo, _bare = _bootstrap(tmp_path)
    _git(repo, "checkout", "-q", "master")
    ok, err = merge_feature_deterministically(
        repo, integration_branch="master", feature_branch="feature/rm-x"
    )
    assert ok, err
    assert not registry_path(repo).exists()
    assert not (repo / "roadmap.md").exists()


def test_codename_from_branch() -> None:
    assert codename_from_branch("feature/rm-alpha") == "alpha"
    assert codename_from_branch("feature/other") is None
    assert codename_from_branch("feature/rm-") is None
