"""Tests for the one project-root resolver.

Both layouts have to resolve identically from any working directory, for the
CLI and the GUI alike. Before this existed the two surfaces disagreed: the GUI
read ``SPECY_ROAD_REPO_ROOT`` and discovered upward, the CLI did neither, so a
nested project needed an explicit ``--repo-root`` on every single invocation.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from specy_road.runtime_paths import (
    discover_project_root,
    git_root,
    prefix_within,
    project_prefix,
    project_root,
    recorded_project_root,
    source_scan_root,
)


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def _repo(tmp_path: Path, project: str = ".") -> tuple[Path, Path]:
    """A git checkout, plus its project tree — embedded or nested."""
    top = tmp_path / "checkout"
    top.mkdir()
    _git(top, "init", "-q", "-b", "main")
    proj = (top / project).resolve() if project != "." else top.resolve()
    (proj / "roadmap").mkdir(parents=True)
    (proj / "roadmap" / "manifest.json").write_text(
        json.dumps({"version": 1, "includes": []}), encoding="utf-8"
    )
    return top.resolve(), proj


def _record(top: Path, value: str) -> None:
    path = top / ".specyrd" / "manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"project_root": value}), encoding="utf-8")


# --- precedence, one test per step ------------------------------------------


def test_explicit_repo_root_wins_over_everything(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    top, _proj = _repo(tmp_path, "sr")
    _record(top, "sr")
    monkeypatch.setenv("SPECY_ROAD_REPO_ROOT", str(top))
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()

    assert project_root(elsewhere) == elsewhere.resolve()


def test_env_var_wins_over_the_recorded_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The CLI ignored this variable entirely, while the docs told people to set it."""
    top, proj = _repo(tmp_path, "sr")
    _record(top, "sr")
    other = tmp_path / "other"
    other.mkdir()
    monkeypatch.chdir(top)
    monkeypatch.setenv("SPECY_ROAD_REPO_ROOT", str(other))

    assert project_root() == other.resolve()
    assert project_root() != proj


def test_recorded_root_wins_over_discovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two roadmaps in one repo: the recorded one must win, not whichever is nearer.

    This is the whole reason the layout is recorded rather than scanned for.
    """
    top, proj = _repo(tmp_path, "sr")
    decoy = top / "vendor" / "other"
    (decoy / "roadmap").mkdir(parents=True)
    (decoy / "roadmap" / "manifest.json").write_text("{}", encoding="utf-8")
    _record(top, "sr")
    monkeypatch.chdir(decoy)

    assert project_root() == proj


def test_discovery_finds_a_nested_project_from_inside_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    top, proj = _repo(tmp_path, "sr")
    deeper = proj / "roadmap"
    monkeypatch.chdir(deeper)

    assert project_root() == proj
    assert top != proj  # genuinely nested


def test_falls_back_to_the_git_root_with_no_roadmap_anywhere(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    top = tmp_path / "checkout"
    (top / "src").mkdir(parents=True)
    _git(top, "init", "-q", "-b", "main")
    monkeypatch.chdir(top / "src")

    assert project_root() == top.resolve()


def test_falls_back_to_cwd_outside_a_git_worktree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A brief must still render for someone who unzipped a project."""
    plain = tmp_path / "plain"
    plain.mkdir()
    monkeypatch.chdir(plain)

    assert project_root() == plain.resolve()


# --- the CLI and the GUI must agree -----------------------------------------


def test_the_gui_resolves_exactly_what_the_cli_resolves(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The split this change exists to close."""
    from specy_road.gui_app_helpers import get_repo_root

    top, proj = _repo(tmp_path, "sr")
    _record(top, "sr")
    monkeypatch.chdir(top)

    assert get_repo_root() == project_root() == proj


# --- the two roots ----------------------------------------------------------


def test_project_prefix_bridges_the_two_roots(tmp_path: Path) -> None:
    top, proj = _repo(tmp_path, "sr")
    _git(top, "add", "-A")
    _git(top, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "x")

    assert project_prefix(proj) == "sr/"
    assert project_prefix(top) == ""


def test_prefix_within_works_before_anything_is_committed(tmp_path: Path) -> None:
    """``init`` needs the prefix while the tree is still untracked."""
    top, proj = _repo(tmp_path, "sr")

    assert prefix_within(top, proj) == "sr/"
    assert prefix_within(top, top) == ""


def test_a_recorded_root_may_not_escape_its_checkout(tmp_path: Path) -> None:
    """A traversal in the manifest must not redirect every command elsewhere."""
    top, _proj = _repo(tmp_path, "sr")
    _record(top, "../../etc")

    assert recorded_project_root(top) is None


def test_a_recorded_root_that_no_longer_exists_is_ignored(tmp_path: Path) -> None:
    top, _proj = _repo(tmp_path, "sr")
    _record(top, "moved-away")

    assert recorded_project_root(top) is None


def test_embedded_records_as_dot_and_reads_back_as_absent(tmp_path: Path) -> None:
    top, _proj = _repo(tmp_path)
    _record(top, ".")

    assert recorded_project_root(top) is None  # "." means "same as git root"


# --- source_scan_root -------------------------------------------------------


def test_source_globs_anchor_at_the_git_root_for_a_nested_project(
    tmp_path: Path,
) -> None:
    """Otherwise `frontend/**` matches nothing and file-limits enforces nothing."""
    top, proj = _repo(tmp_path, "sr")
    _record(top, "sr")

    assert source_scan_root(proj) == top


def test_source_globs_stay_put_for_an_ad_hoc_subdirectory(tmp_path: Path) -> None:
    """`--repo-root <fixture>` must scan that subtree, not the checkout above it."""
    top, _proj = _repo(tmp_path)
    fixture = top / "tests" / "fixtures" / "sample"
    (fixture / "roadmap").mkdir(parents=True)

    assert source_scan_root(fixture) == fixture.resolve()


def test_source_globs_are_unchanged_for_an_embedded_project(tmp_path: Path) -> None:
    top, proj = _repo(tmp_path)

    assert source_scan_root(proj) == top


# --- discovery --------------------------------------------------------------


def test_discovery_returns_none_when_there_is_no_roadmap(tmp_path: Path) -> None:
    assert discover_project_root(tmp_path) is None


def test_git_root_returns_none_outside_a_worktree(tmp_path: Path) -> None:
    assert git_root(tmp_path) is None
