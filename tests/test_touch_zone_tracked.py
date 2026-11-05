"""Touch zones are checked against ``git ls-files`` when they are written.

A zone written as a name prefix (``pkg/worker_ops_``) is read by the matcher as a
literal path, so it matched nothing and executors stopped for files "outside
their zones". ``validate`` warns about such a zone with the glob to use, and
notices every other open node's zone that matches no tracked file and is not a
directory, Not Started included; ``add-node`` and ``edit-node`` warn about the
zones of the node they wrote.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from specy_road.bundled_scripts.touch_zone_tracked import (
    tracked_files,
    untracked_zones,
    warn_untracked_zones,
    warn_written_zones,
)
from tests.helpers import BUNDLED_SCRIPTS, script_subprocess_env
from tests.integrity_repo_helpers import git
from tests.test_roadmap_crud import crud_fixture_repo, run_crud

FILES = ("pkg/worker_ops_launch.py", "pkg/worker_ops_stop.py", "pkg/core.py", "docs/a.md")
UNTRACKED = "touch zones that match no tracked file and are not a directory"


def zone_git_repo(root: Path, files=FILES) -> Path:
    for rel in files:
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text("x = 1\n", encoding="utf-8")
    git(root, "init", "-q")
    git(root, "config", "user.email", "t@e.com")
    git(root, "config", "user.name", "T")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "init")
    return root


def _node(zones: list[str], status: str = "Not Started", nid: str = "M1.1") -> dict:
    return {"id": nid, "status": status, "touch_zones": zones}


def test_a_name_prefix_is_named_with_the_glob_to_use(tmp_path: Path, capsys) -> None:
    zone_git_repo(tmp_path)

    warn_untracked_zones([_node(["pkg/worker_ops_"])], tmp_path)

    out, err = capsys.readouterr()
    assert "M1.1 touch zone 'pkg/worker_ops_' is a name prefix of 2 tracked file(s)" in err
    assert "'pkg/worker_ops_*.py'" in err
    assert "prefix is read as a literal path and is not supported" in err
    assert out == ""   # the prefix line covers it; one line per zone
    assert len(err.strip().splitlines()) == 1   # add-node/edit-node re-print only lines saying "warning"
    assert "warning" in err


def test_missing_paths_and_unmatched_globs_on_open_nodes_share_one_notice(tmp_path: Path, capsys) -> None:
    zone_git_repo(tmp_path)
    nodes = [
        _node(["pkg/new_module.py", "pkg/core.py"]),
        _node(["pkg/nope_*.py", "pkg/worker_ops_*.py"], status="In Progress", nid="M1.2"),
    ]

    warn_untracked_zones(nodes, tmp_path, claims=[{"node_id": "M1.1"}])   # claimed: named, not counted

    out, err = capsys.readouterr()
    assert err == ""   # stdout: --strict counts stderr lines, and new-file zones are expected
    assert out.count("\n") == 1
    assert f"roadmap: notice — {UNTRACKED}: M1.1 'pkg/new_module.py'; M1.2 'pkg/nope_*.py'." in out
    assert "Keep a zone that names a file the work will create" in out
    assert "a bare name prefix is read as a literal path and is not supported" in out


def test_the_written_node_s_zones_are_a_stderr_warning(tmp_path: Path, capsys) -> None:
    zone_git_repo(tmp_path)

    warn_written_zones("M1.1", ["pkg/new_module.py", "pkg/core.py", "pkg/worker_ops_"], tmp_path)

    out, err = capsys.readouterr()
    assert out == ""
    assert err.startswith(f"roadmap: warning — {UNTRACKED}: M1.1 'pkg/new_module.py'. Keep a zone")
    assert err.count("\n") == 1   # the prefix zone is validate's line, not this one


@pytest.mark.parametrize("zone", ["pkg/core.py", "pkg", "pkg/", "pkg/worker_ops_*.py", "pkg/worker_ops_*", "docs"])
def test_files_directories_and_matching_globs_are_quiet(tmp_path: Path, capsys, zone: str) -> None:
    zone_git_repo(tmp_path)

    warn_untracked_zones([_node([zone])], tmp_path)

    assert capsys.readouterr() == ("", "")


def test_settled_nodes_are_left_alone(tmp_path: Path, capsys) -> None:
    zone_git_repo(tmp_path)

    warn_untracked_zones([_node(["pkg/worker_ops_", "pkg/gone.py"], status="Complete")], tmp_path)

    assert capsys.readouterr() == ("", "")


def test_outside_git_the_check_is_silent(tmp_path: Path, capsys) -> None:
    assert tracked_files(tmp_path) is None
    warn_untracked_zones([_node(["pkg/worker_ops_", "pkg/missing.py"])], tmp_path)
    warn_written_zones("M1.1", ["pkg/missing.py"], tmp_path)
    assert capsys.readouterr() == ("", "")


def test_untracked_zones_keep_globs_and_directories_and_leave_prefixes_out(tmp_path: Path) -> None:
    zone_git_repo(tmp_path)
    (tmp_path / "work").mkdir()   # a directory with no tracked file is still a directory
    tracked = tracked_files(tmp_path)

    zones = ["pkg/core.py", "pkg/", "work/", "pkg/*.py", "pkg/nope_*.py", "pkg/new.py", "pkg/worker_ops_", "../x"]

    assert untracked_zones(zones, tracked) == ["pkg/nope_*.py", "pkg/new.py", "../x"]


def test_a_nested_project_matches_zones_from_either_root(tmp_path: Path) -> None:
    zone_git_repo(tmp_path, files=("sr/schemas/a.json", "pkg/core.py"))
    tracked = tracked_files(tmp_path / "sr")

    assert untracked_zones(["schemas/a.json", "sr/schemas/a.json", "pkg/core.py"], tracked) == []
    assert untracked_zones(["schemas/b.json"], tracked) == ["schemas/b.json"]


@pytest.fixture
def crud_git_repo(tmp_path: Path) -> Path:
    crud_fixture_repo(tmp_path)
    return zone_git_repo(tmp_path)


def _validate(root: Path, *flags: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(BUNDLED_SCRIPTS / "validate_roadmap.py"), "--repo-root", str(root), *flags],
        cwd=root, capture_output=True, text=True, env=script_subprocess_env(),
    )


def _edit(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return run_crud(root, "--repo-root", str(root), "edit-node", "M99.1", *args)


def test_validate_reports_a_not_started_node_s_missing_path_and_unmatched_glob(crud_git_repo: Path) -> None:
    r = _edit(crud_git_repo, "--set", "touch_zones=pkg/missing.py,pkg/core.py")
    assert r.returncode == 0, r.stderr
    r = _edit(crud_git_repo, "--add", "touch_zones=pkg/nope_*.py")
    assert r.returncode == 0, r.stderr

    v = _validate(crud_git_repo)
    assert f"roadmap: notice — {UNTRACKED}: 1 node(s) (by status: Not Started 1);" in v.stdout   # counted only
    v = _validate(crud_git_repo, "--all")

    assert v.returncode == 0, v.stderr
    assert "OK: roadmap and registry validate." in v.stdout
    assert f"roadmap: notice — {UNTRACKED}: M99.1 'pkg/missing.py', 'pkg/nope_*.py'." in v.stdout
    assert "Keep a zone that names a file the work will create" in v.stdout
    assert "'pkg/core.py'" not in v.stdout + v.stderr


def test_validate_strict_does_not_fail_on_a_zone_the_work_will_create(crud_git_repo: Path) -> None:
    assert _edit(crud_git_repo, "--set", "touch_zones=pkg/new_module.py").returncode == 0

    v = _validate(crud_git_repo, "--strict")

    assert UNTRACKED in v.stdout
    assert "touch zone" not in v.stderr   # this fixture's other warnings fail --strict on their own


def test_validate_names_a_prefix_zone_with_its_glob(crud_git_repo: Path) -> None:
    assert _edit(crud_git_repo, "--set", "touch_zones=pkg/worker_ops_").returncode == 0

    v = _validate(crud_git_repo, "--strict")

    assert v.returncode == 1   # a prefix is never a file the work will create
    assert "M99.1 touch zone 'pkg/worker_ops_' is a name prefix" in v.stderr
    assert "Use 'pkg/worker_ops_*.py'" in v.stderr


def test_validate_is_quiet_for_good_zones(crud_git_repo: Path) -> None:
    assert _edit(crud_git_repo, "--set", "touch_zones=pkg/core.py,pkg/worker_ops_*.py,docs/").returncode == 0

    v = _validate(crud_git_repo)

    assert v.returncode == 0, v.stderr
    assert "touch zone" not in v.stdout + v.stderr


def _add(root: Path, *zones: str):
    args = [a for z in zones for a in ("--touch-zone", z)]
    return run_crud(root, "--repo-root", str(root), "add-node", "--id", "M99.3", "--type", "task",
                    "--title", "Three", "--parent-id", "M99", *args)


def test_add_node_warns_on_a_prefix_and_an_untracked_zone(crud_git_repo: Path) -> None:
    r = _add(crud_git_repo, "pkg/worker_ops_", "pkg/new_module.py", "pkg/core.py", "pkg/worker_ops_*.py")

    assert r.returncode == 0, r.stderr
    assert "M99.3 touch zone 'pkg/worker_ops_' is a name prefix" in r.stderr
    assert "Use 'pkg/worker_ops_*.py'" in r.stderr
    assert f"{UNTRACKED}: M99.3 'pkg/new_module.py'." in r.stderr
    assert "'pkg/core.py'" not in r.stderr


def test_edit_node_warns_only_when_it_writes_zones(crud_git_repo: Path) -> None:
    r = _edit(crud_git_repo, "--set", "touch_zones=pkg/new_module.py,pkg/core.py")
    assert r.returncode == 0, r.stderr
    assert f"roadmap: warning — {UNTRACKED}: M99.1 'pkg/new_module.py'." in r.stderr
    assert r.stderr.count(UNTRACKED) == 1

    r = _edit(crud_git_repo, "--set", "title=One renamed")
    assert r.returncode == 0, r.stderr
    assert UNTRACKED not in r.stderr

    r = _edit(crud_git_repo, "--set", "touch_zones=pkg/worker_ops_")
    assert r.returncode == 0, r.stderr
    assert "M99.1 touch zone 'pkg/worker_ops_' is a name prefix" in r.stderr
    assert UNTRACKED not in r.stderr   # the prefix line already covers it
