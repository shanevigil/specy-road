"""Touch zones are checked against ``git ls-files`` when they are written.

A zone written as a name prefix (``pkg/worker_ops_``) is read by the matcher as a
literal path, so it matched nothing and executors stopped for files "outside
their zones". ``validate`` now names such a zone with the glob to use, and
``add-node`` / ``edit-node`` name a zone of the node they wrote that matches no
tracked file and is not a directory.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from specy_road.bundled_scripts.touch_zone_tracked import (
    tracked_files,
    untracked_zones,
    warn_zone_prefixes,
)
from tests.integrity_repo_helpers import git
from tests.test_roadmap_crud import crud_fixture_repo, run_crud

FILES = ("pkg/worker_ops_launch.py", "pkg/worker_ops_stop.py", "pkg/core.py", "docs/a.md")


def _git_repo(root: Path, files=FILES) -> Path:
    for rel in files:
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text("x = 1\n", encoding="utf-8")
    git(root, "init", "-q")
    git(root, "config", "user.email", "t@e.com")
    git(root, "config", "user.name", "T")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "init")
    return root


def _node(zones: list[str], status: str = "Not Started") -> dict:
    return {"id": "M1.1", "status": status, "touch_zones": zones}


def test_a_name_prefix_is_named_with_the_glob_to_use(tmp_path: Path, capsys) -> None:
    _git_repo(tmp_path)

    warn_zone_prefixes([_node(["pkg/worker_ops_"])], tmp_path)

    err = capsys.readouterr().err
    assert "M1.1 touch zone 'pkg/worker_ops_' is a name prefix of 2 tracked file(s)" in err
    assert "'pkg/worker_ops_*.py'" in err
    assert "prefix is read as a literal path and is not supported" in err
    assert len(err.strip().splitlines()) == 1   # add-node/edit-node re-print only lines saying "warning"
    assert "warning" in err


@pytest.mark.parametrize(
    "zone",
    ["pkg/core.py", "pkg", "pkg/", "pkg/worker_ops_*.py", "pkg/worker_ops_*", "pkg/new_module.py", "pkg/worker_ops/"],
)
def test_files_directories_globs_and_new_files_are_not_prefixes(tmp_path: Path, capsys, zone: str) -> None:
    _git_repo(tmp_path)

    warn_zone_prefixes([_node([zone])], tmp_path)

    assert capsys.readouterr().err == ""


def test_settled_nodes_are_left_alone(tmp_path: Path, capsys) -> None:
    _git_repo(tmp_path)

    warn_zone_prefixes([_node(["pkg/worker_ops_"], status="Complete")], tmp_path)

    assert capsys.readouterr().err == ""


def test_outside_git_both_checks_are_silent(tmp_path: Path, capsys) -> None:
    assert tracked_files(tmp_path) is None
    warn_zone_prefixes([_node(["pkg/worker_ops_"])], tmp_path)
    assert untracked_zones(["pkg/missing.py"], tmp_path) == []
    assert capsys.readouterr().err == ""


def test_untracked_zones_keep_globs_and_directories_and_leave_prefixes_to_validate(tmp_path: Path) -> None:
    _git_repo(tmp_path)
    (tmp_path / "work").mkdir()   # a directory with no tracked file is still a directory

    zones = ["pkg/core.py", "pkg/", "work/", "pkg/*.py", "pkg/nope_*.py", "pkg/new.py", "pkg/worker_ops_", "../x"]

    assert untracked_zones(zones, tmp_path) == ["pkg/nope_*.py", "pkg/new.py", "../x"]


def test_a_nested_project_matches_zones_from_either_root(tmp_path: Path) -> None:
    _git_repo(tmp_path, files=("sr/schemas/a.json", "pkg/core.py"))
    project = tmp_path / "sr"

    assert untracked_zones(["schemas/a.json", "sr/schemas/a.json", "pkg/core.py"], project) == []
    assert untracked_zones(["schemas/b.json"], project) == ["schemas/b.json"]


@pytest.fixture
def crud_git_repo(tmp_path: Path) -> Path:
    crud_fixture_repo(tmp_path)
    return _git_repo(tmp_path)


def _add(root: Path, *zones: str):
    args = [a for z in zones for a in ("--touch-zone", z)]
    return run_crud(root, "--repo-root", str(root), "add-node", "--id", "M99.3", "--type", "task",
                    "--title", "Three", "--parent-id", "M99", *args)


def test_add_node_warns_on_a_prefix_and_an_untracked_zone(crud_git_repo: Path) -> None:
    r = _add(crud_git_repo, "pkg/worker_ops_", "pkg/new_module.py", "pkg/core.py", "pkg/worker_ops_*.py")

    assert r.returncode == 0, r.stderr
    assert "M99.3 touch zone 'pkg/worker_ops_' is a name prefix" in r.stderr
    assert "Use 'pkg/worker_ops_*.py'" in r.stderr
    assert "M99.3 touch zone(s) match no tracked file and are not a directory: 'pkg/new_module.py'." in r.stderr
    assert "'pkg/core.py'" not in r.stderr
    assert "Keep a zone that names a file this work will create" in r.stderr


def test_add_node_with_good_zones_is_quiet(crud_git_repo: Path) -> None:
    r = _add(crud_git_repo, "pkg/core.py", "pkg/worker_ops_*.py", "docs/")

    assert r.returncode == 0, r.stderr
    assert "touch zone" not in r.stderr


def test_edit_node_warns_only_when_it_writes_zones(crud_git_repo: Path) -> None:
    def edit(value: str):
        return run_crud(crud_git_repo, "--repo-root", str(crud_git_repo), "edit-node", "M99.1", "--set", value)

    r = edit("touch_zones=pkg/new_module.py,pkg/core.py")
    assert r.returncode == 0, r.stderr
    assert "M99.1 touch zone(s) match no tracked file and are not a directory: 'pkg/new_module.py'." in r.stderr

    r = edit("title=One renamed")
    assert r.returncode == 0, r.stderr
    assert "match no tracked file" not in r.stderr

    r = edit("touch_zones=pkg/worker_ops_")
    assert r.returncode == 0, r.stderr
    assert "M99.1 touch zone 'pkg/worker_ops_' is a name prefix" in r.stderr
    assert "match no tracked file" not in r.stderr   # the prefix line already covers it
